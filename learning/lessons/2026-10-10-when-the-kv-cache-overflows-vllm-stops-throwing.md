In the last phase you priced a rented GPU box and worked out how much KV cache, the attention keys and values the GPU keeps for each request, fits in the card's memory. You could predict exactly when the cache fills, and what it costs when it does: an old conversation's blocks are dropped, and its next message pays a full new prefill. Now put that box under a multi-turn chat workload: 12K-token conversations, 8 rounds each, with the number of simultaneous conversations climbing from 16 toward 512. Somewhere on that climb your model says throughput collapses into repeated prefill, and there is nothing in between.

That answer turns out to be wrong in a useful way. A serving system does not have to drop an evicted block. It can copy it somewhere slower and cheaper, and read it back later for much less than a recompute. The question this lesson teaches you to ask of any serving system is not "how much cache does it have" but "how many places can a block live, and what does it cost to get one back from each?"

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- A full KV cache is a demotion problem, not a loss: a hit on a slow tier costs a PCIe read, and recompute costs a full GPU prefill. Predict any serving system's scaling curve by counting its tiers and the cost of a hit on each.

## What happens on his box when conversation 65 arrives

When your cache overflows, vLLM can demote blocks to slower memory instead of dropping them. The cost gap is large.

You are serving multi-turn chat on the rented box from your phase. Each conversation starts with a 12K-token prompt and runs 8 rounds, and the load is climbing from 16 simultaneous conversations toward 512. Your phase gave you a sharp prediction of what happens as it climbs. Recall the two numbers it used. The KV cache, the attention keys and values the GPU keeps for each request, must sit in the card's HBM, and it is finite. The prefill, the first pass that computes the KV cache from the prompt tokens, is the expensive pass. In your phase's model, a full cache means an old conversation's blocks are dropped, and its next message pays a full recompute of tens of thousands of prompt tokens.

Predict: at 64 concurrent conversations, HBM already holds every active cache. How much does adding a CPU offload tier change throughput?Almost nothing, and the reason is that a tier only earns anything when the tier above it misses. At 64 conversations every live prefix is already in HBM, so no request ever looks one tier down. Offloading pays from 65 upward, when HBM starts evicting. This matches vLLM's own benchmark, which saw no gain until roughly 64 conversations (details in the evidence below).

Now walk the same climb with tiered offloading, which copies evicted cache blocks to cheaper memory instead of dropping them. The picture is a memory hierarchy, the same shape as your box's page cache above its disk, applied to KV blocks.

  GPU HBM · active caches
  fastest, smallest, holds ~64 conversations

  CPU DRAM · LRU policy
  cheaper, larger, reload is a PCIe read

  Filesystem · NVMe
  cheapest, near-unlimited, slowest reload

  evict: copy
  to tier below

  reload on hit:
  through DRAM first

  miss on all tiers: recompute the full prefill on the GPU

The three places a KV block can live, from fastest and smallest to cheapest and largest.

With that picture, the climb through your load range reads differently.

- From 16 to about 64 conversations, HBM holds every active cache, so both models behave identically and offloading sits idle.

- From 64 to about 128, HBM fills and eviction starts, but each evicted block is copied to host DRAM first. A conversation returning for round 5 reads its prefix back over PCIe instead of recomputing 12,288 prompt tokens on the GPU, so throughput holds.

- Past about 128, DRAM also fills and blocks demote to the filesystem tier. A hit there is slower than a DRAM hit, but it still beats a full prefill, because conversation 65 and conversation 400 share the same cost question, answered from disk.

Vendors report this gap in concrete numbers. vLLM's own benchmark used Qwen3.6-35B-A3B on 2x H100, the same 12K-prompt 8-round shape as your workload. Throughput collapsed without offloading past 64 conversations. It held with the CPU tier. It more than doubled with the storage tier past roughly 128. The same direction appears in NVIDIA's and Moonshot AI's separate systems.

EvidenceThe thresholds and the 2x figure come only from the vLLM team's blog and their own repro repository, and that repo discloses a concurrency bug in its test harness. Treat the direction (a storage hit beats recompute at scale) as well supported and the exact curve as unverified. NVIDIA Dynamo ships the same GPU-to-CPU-to-disk design independently, and the Mooncake paper reports the same idea at production scale.

The wrong belief your phase left you with was reasonable at the time. Evicted blocks are gone, so the only fixes were more GPUs or smaller prompts. That belief describes a cache with one tier, and serving systems do not have to have one tier.

A full KV cache is a demotion problem; a slow-tier hit costs a PCIe read, recompute costs a full prefill.

Thinking evicted blocks are lost, so you buy GPUs for a problem a copy to host memory solves.

Sketch your own workload's three tiers and mark which tier each conversation count would be reading from.

Demotion exists, but existing is not the same as paying off. The next section gives you the formula for when a tier earns its place. It is hit rate times the gap between reload cost and recompute cost.

## Why the value of a tier is hit rate times the gap

A tier earns its place only when its hits outweigh what each hit costs.

The section above showed the demotion happens, but not when it pays. The answer is one multiplication. Take one full prefill of your 12,288-token prompt as the unit of cost. The recompute cost is paying that whole pass again on the GPU because the prefix's KV cache was evicted. Call it 1 in these units. The reload cost is reading the stored blocks back from a lower tier. From host DRAM that is a fast PCIe copy, and from the filesystem tier a slower read. Per request, a tier saves this:

saving per request = hit rate × (recompute cost − reload cost)

Hit rate is the share of all requests the tier serves. It multiplies the gap. So a fast tier that rarely hits can lose to a slow tier that hits on nearly every request.

Predict: Tier A reloads in 10% of a prefill and hits on 20% of requests. Tier B reloads in 50% of a prefill and hits on 80%. At 96 conversations, which tier saves more per request?
Set recompute cost to 1 and compute both tiers.

Tier A   0.20 × (1 − 0.10) = 0.18 prefill saved per request
Tier B   0.80 × (1 − 0.50) = 0.40 prefill saved per request

Tier B saves 2.2 times more per request, because it hits four times as often. Its per-hit saving falls only from 0.90 to 0.50. Over 100 requests that is 40 prefills of GPU time against 18. The fast pick was reasonable. Reload speed shows up as latency on every miss, while hit rate stays invisible until you count requests.

Set the sliders to Tier B's 80 and 50 and check the results against the boxed numbers.

  Saving per request, in prefills

  Hit rate
     % of requests
  Reload cost
     % of one prefill
  Saving on each hit

  Saving per request

Now read the benchmark through the formula: Qwen3.6-35B-A3B on 2 H100s. It uses 12K-token prompts over 8 rounds, with concurrency rising from 16 toward 512. Below about 64 conversations, HBM already holds every active prefix. The offload tiers see a hit rate of zero, and zero times any gap is zero. Every configuration overlaps below 64, because nothing misses and nothing needs saving. From 64 to 128 the CPU tier serves evicted prefixes at PCIe cost, keeping nearly the whole gap. Past about 128 the filesystem tier serves them at higher reload cost. So the gap shrinks, and a storage-backed box never reaches peak throughput. Each hit still avoids recomputing 12,288 prompt tokens, so throughput more than doubles there.

EvidenceThe 64 and 128 thresholds and the doubling figure come only from the vLLM team's blog and their own repro repo, which discloses a harness concurrency bug. NVIDIA Dynamo's docs and the Mooncake paper support the direction, not the numbers.

The configuration encodes the same arithmetic. In vLLM's offloading guide at main, offload_prompt_only defaults to true. So only prefill blocks are offloaded, and decode-time KV is skipped. Every one of your 8 rounds re-reads the same prompt prefix. So its hit rate is high, and its recompute cost the full pass. KV written while generating one reply is never re-read. So its hit rate sits near zero, and storing it pays only for the copy.

A tier is worth hit rate times the gap between recompute cost and reload cost.

Judging tiers by speed alone, and dropping the slow storage tier that wins at scale.

Drag hit rate to zero and the saving vanishes, exactly the story below 64 conversations.

The formula prices each tier, not the machinery that moves blocks between them. The next section answers how a slow disk avoids stalling the GPU and how two servers share one cached prompt.

## The two design choices that keep the GPU out of trouble

The formula says offloading pays at scale, but it leaves two questions open. Why does a slow disk not slow the GPU, and how can two servers share cached prompts?

On your box the filesystem tier is a plain NVMe drive. A disk read can take milliseconds where an HBM copy takes microseconds. If GPU memory stayed reserved while the disk worked, one slow drive could stall your whole serving loop. The Naive belief is that the transfer layer must be fast to keep the GPU fast. What actually happens is that the design removes the GPU from the transfer entirely.

### Host-centric staging

Host-centric staging is the rule that only the CPU tier may touch GPU memory. Every secondary tier works on host DRAM alone. The GPU hands its evicted KV blocks to the CPU tier. It is freed immediately, before any disk or network write starts. On reload the order reverses. GPU memory is allocated only after the data already sits in host memory, a just-in-time allocation.

- GPU to DRAMthe only copy that touches GPU memory; then GPU memory is freed

- DRAM to diska plain CPU process writes with POSIX I/O, at disk speed

- reloaddisk to DRAM first, then DRAM to GPU once the data is ready

The consequence is exact. A slow disk can delay a reload. But it cannot extend how long GPU memory is held, because GPU memory is released in step one. The vLLM docs state it as a rule. Secondary tiers cannot read from or write to GPU memory. Every GPU-to-secondary transfer is staged through the CPU primary tier.

### Content addressing

The second choice answers the sharing question. Content addressing means the filesystem tier names each stored chunk by a hash of its token content, not by which request produced it. Two prompts with the same prefix produce the same hash, so two vLLM instances on one shared mount read each other's cached chunks with no coordination, no registry and no lock.

This has a sharp edge. The default block-hash seed is fixed, so sharing works out of the box. But the xxhash prefix-caching algorithms use a random seed chosen per process. So two instances hash the same tokens to different keys, and every cross-instance read misses. The docs' fix is one environment variable: set the same PYTHONHASHSEED on every instance.

- Same prompt, two boxes, does box B hit?

- default hash or same PYTHONHASHSEEDidentical content, identical key, hit

- xxhash with per-process seeddifferent keys, a miss on every lookup

EvidenceThe GPU-access rule, the just-in-time reload order and the PYTHONHASHSEED caveat are verbatim from the vLLM usage guide at main, read 2026-10-09. RFC issue 38260 confirms secondary tiers never touch accelerator memory. NVIDIA Dynamo's independent docs describe the same host-first design.

Only the CPU tier touches the GPU, and chunks are named by content so sharing needs no coordination.

Enabling xxhash prefix caching on two boxes with default settings: every shared lookup silently misses.

Check PYTHONHASHSEED on any two serving processes you expect to share a mount; mismatched seeds mean zero cross-instance hits.

You can now read the phase's eviction cliff as a demotion path with a recompute fallback, not a wall. HBM is the top tier. DRAM and storage sit below it, and the tier-value formula predicts what each adds. The lab puts you in the actual docs to find these defaults for your own workload.

## Lab

Fifteen minutes in the source doc, so the defaults from this phase are ones you checked yourself. Open the vLLM KV offloading usage guide, the same file the digest read:

https://raw.githubusercontent.com/vllm-project/vllm/main/docs/features/kv_offloading_usage.md

-  L1 offline Find the CPU-tier policy. In the guide's tier configuration section, locate the eviction policy setting. You should find lru as the default, with arc built in. This is the cache behaviour from the sections above: the host tier is a real cache, not a staging buffer.
Answer sketchThe config reference lists the policy key with default lru. If you found it, the claim "the CPU tier is a proper cache" is verified in the doc, not just in this lesson.

-  L2 offline Find the two economics defaults. Locate offload_prompt_only and confirm its default is true, and blocks_per_chunk and confirm its default is 1. Connect each to the tier-value formula from earlier: the first says only the expensive reusable tokens are stored, the second says one chunk is one GPU block, so a miss costs at most the transfer of small blocks until promotion starts.
Answer sketchBoth keys appear with defaults true and 1. If offload_prompt_only were false, decode-time KV would consume DRAM capacity that prompt blocks could have used.

-  L3 offline Apply it to the running case. Write one line for your workload of 12K-token conversations over 8 rounds: which tier above your cache would fill first as concurrency climbs, and what a miss costs today, before any offloading config is set. Use the formula: a miss costs the recompute cost, because there is no tier to pay a reload on.
Answer sketchHBM fills first, because it is the only tier on the box today. A miss on the eviction path costs a full GPU prefill of the 12K-token prompt. After adding a CPU tier, the same miss costs a PCIe read; after a storage tier, a disk read. One line each is enough.

The phase's eviction cliff is now the top tier of a memory hierarchy. When you re-read the phase's capacity math, read the cliff as a demotion path with a recompute fallback, not a wall.

The checkpoint puts this model to work: same shared mount, two GPU boxes, and a cache hit that never happens.

## Checkpoint

The lab checked the defaults on one box. The checkpoint asks what happens when a second box runs the same configuration.

Scenario. Your serving setup adds a second GPU box behind the same shared filesystem mount. Both boxes run xxhash prefix caching with default settings. A prompt cached on box A misses on box B every time, so box B pays a full recompute for prompts box A already holds.

- Using this lesson's model, what causes the miss?

- What single environment variable fixes it?

Answer sketch
The filesystem tier names each chunk by a hash of its token content, so identical prompts share a cache only when both processes produce identical hashes. With the xxhash prefix-caching algorithms the hash seed is random per process, so box A and box B compute different keys for the same prompt. Every lookup on box B misses, and the miss costs a full GPU prefill of the 12K-token prompt.

Setting the same PYTHONHASHSEED on both boxes makes the seeds agree, the keys match, and the shared mount starts behaving as one shared cache.

The default block-hash seed is fixed, so this trap only appears when you choose an xxhash algorithm. The docs' cross-process sharing section states it in one sentence, and it costs exactly one environment variable.

The post turns both results into two publishable claims, one of them a caution about the benchmark numbers.

## Post

Two posts this phase supports.

- "Offload shows no gain at low concurrency, and that is the point." A one-screen note on the tier-value formula: a tier is worth hit rate times the gap between recompute cost and reload cost, so when HBM already holds every active prefix the formula is zero. Yours because it comes from your box: 12K-token conversations, 8 rounds, the threshold where your working set stops fitting.

- "The 2x long-context offload number is single-vendor." A short caution that the threshold numbers (~64, ~128 conversations, more than 2x throughput) come from one team's benchmark of their own feature, and their repro repo discloses a harness bug that could stall concurrency. The direction is supported, the curve is not.

Evidence
The thresholds and 2x figure are reported by the vLLM team's blog post. It reports Qwen3.6-35B-A3B, 2x H100, 12K-token prompts over 8 rounds. Their own repro repo, neuralmagic/fs-offload-experiments, discloses the harness concurrency bug. No independent replication exists. The mechanism is confirmed independently by the vLLM usage guide, RFC issue 38260, NVIDIA Dynamo docs, and the Mooncake paper. See Sources below.

## Sources

- https://vllm.ai/blog/2026-09-10-tiered-kv-offloading: the main text. Gave the tiered framework, the host-centric design, and the benchmark with the ~64 and ~128 thresholds and the 2x figure. Those numbers are authors-only, not independently confirmed.

- https://raw.githubusercontent.com/vllm-project/vllm/main/docs/features/kv_offloading_usage.md: the official usage guide. Confirmed the mechanism: the CPU tier alone touches GPU memory, the lru default, offload_prompt_only: true, blocks_per_chunk: 1, and the PYTHONHASHSEED caveat for cross-instance sharing.

- https://github.com/vllm-project/vllm/issues/38260: the design RFC. Confirmed the public design and carried one independent production datapoint: byte-identical chunks across TP ranks, about 38x fewer CPU bytes.

- https://docs.nvidia.com/dynamo/v-0-9-0/user-guides/kv-cache-offloading: a second vendor shipping the same GPU to CPU to disk tiering. Independent confirmation of the mechanism, plus two caveats the blog omits: an SSD-wear filter and cases where TTFT gains do not appear.

- https://arxiv.org/abs/2407.00079: the Mooncake paper. A different team's production system built on the same idea, so the mechanism has four independent sources. Says nothing about vLLM's numbers.

- https://github.com/neuralmagic/fs-offload-experiments: the authors' own repro repo. Confirms the benchmark method and discloses a harness concurrency bug, so the exact curve stays unverified.

Two things stayed unverified: the claim that the feature landed in vLLM v0.22, and the raw chart values behind the thresholds. The mechanism is high confidence, the 2x curve is not.
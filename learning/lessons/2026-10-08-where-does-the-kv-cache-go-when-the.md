In the last phase you saw prefix caching make a repeated prompt nearly free: the KV blocks, the attention keys and values computed for each token, stay in GPU memory and the next request reuses them instead of computing them again. That works while the blocks fit. Your chat service keeps 12,288 tokens of history per conversation and grows by 4,096 tokens each round, and a GPU holds only so many of those blocks. When 200 conversations run at once, the memory fills, and the serving engine quietly deletes the oldest blocks to make room. The next turn of that conversation then recomputes 12,000 tokens it already computed once, and your users feel it as a multi-second pause before the first word.

So the question this lesson answers: when the GPU runs out of room, does the deleted work have to be deleted forever? It turns out those blocks can be moved, not destroyed: first into ordinary CPU memory, then onto local disk, and brought back when the conversation resumes. That changes how you size a serving setup, because capacity stops being "how much fits on the GPU" and becomes "how much KV data fits across all three places". It also has a catch, because pulling blocks back from disk is not free, and sometimes recomputing is the better deal. By the end you will be able to say which one wins, with numbers.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- When the KV cache outgrows GPU memory, evicted blocks can spill to CPU DRAM and disk instead of being lost, so a service's capacity is set by total KV bytes across tiers, not by HBM alone. Predict which tier limits his serving capacity at a given concurrency, and decide whether enabling CPU offload is worth it for his traffic.

## What happens to an evicted block now

Evicted KV blocks move down a hierarchy of memory tiers instead of being lost.

The phase gave you a simple model of the KV cache, the attention keys and values the GPU keeps for each request. It also gave you prefix caching, the reuse of one prompt's KV blocks when the same prompt appears again. In that model the GPU memory was the whole cache. A hit cost almost nothing, and an eviction meant recompute. That model was accurate for vLLM until recently.

Your running case shows where it breaks. Two hundred conversations of 12,288 tokens each do not fit in GPU memory at once. The engine evicts the oldest conversation, and its next turn recomputes 12,288 tokens. The change is that an evicted block is moved, not deleted. It lands in host DRAM, then optionally on disk or object storage. The whole chain is called a tiered KV cache, a cache whose blocks live across GPU, CPU and storage tiers under one lookup.

GPU HBMhot blocks, serves hits directly
CPU DRAMa real LRU/ARC cache
filesystem / object storekeys are token-sequence hashes

spill on eviction (async copy)

reload climbs back up
One request's KV blocks move down on eviction and back up on the next turn. Illustration of the mechanism, not measured.

Two properties make this a cache and not a backup. The host tier is a proper LRU cache, so blocks stay hot in DRAM and serve hits directly. On reload, blocks come back to the GPU only when a request needs them again.

Predict: a conversation's blocks sit on local NVMe. Its next turn arrives. Which is cheaper, reloading 12,288 tokens of KV from disk or recomputing the prompt?
Reloading. A storage-backed hit beats recomputing 12,288 or more tokens from scratch. An independent project, LMCache, measured the same mechanism on Llama-3.1-8B: cold TTFT was 6.314 seconds, a storage-backed hit returned the first token in 0.148 seconds, a factor of 42.6. The details of the transfer path are the subject of the next section.

The consequence for sizing is the loaded sentence of the article. Capacity is set by which tier can hold your working set, not by HBM alone. In the authors' benchmark, HBM alone carried about 64 concurrent conversations of this shape, the CPU tier of 147GB carried 64 to 128, and the disk tier carried the rest.

Evidence
The capacity crossover numbers come from the vLLM blog benchmark: Qwen3.6-35B-A3B on 2x H100 80GB, TP=2, 12,288-token first turns over 8 rounds, concurrency up to 64, CPU tier of 147GB. Only the authors report them; no independent rerun exists. The 6.314s versus 0.148s TTFT figures were measured by LMCache, an independent project, on Llama-3.1-8B in a single-request demo.

An evicted KV block spills to CPU and disk instead of vanishing.

The belief that GPU memory is the whole cache leads you to recompute or buy more GPUs.

Estimate your own KV bytes per token from your model config and multiply by 12,288.

This section said where an evicted block goes, but not how a tier as slow as NVMe can take part without stalling the GPU. The next section answers that.

## Why the GPU never waits on the disk

A disk tier only works if the GPU never stops to wait for it.

The tiered KV cache above holds one design problem. A reload from NVMe takes far longer than a decode step. So a naive design would pause every stream while 12,288 tokens of KV travel upward. vLLM's answer is a rule about where data waits.

Predict: the GPU needs a block of KV that lives on NVMe. Loading it into host DRAM takes 200 milliseconds, and decoding needs GPU blocks every 50 milliseconds. Does the load block decoding?
No. The reload waits in host DRAM, not in GPU memory. Because GPU blocks are allocated only after the copy to host completes. Decoding keeps its blocks the whole time. The paragraphs below show why this rule holds on the way down too.

The rule is host-centric routing. Every byte of KV passes through CPU DRAM on the way out and on the way back. GPU memory is held only while data is physically in it. It works in three steps.

- On eviction, an asynchronous DMA copy moves the block from GPU HBM to host DRAM. This is the spill, the copy down to host that replaces deletion.

- The GPU block is freed the moment that copy completes, which the authors state happens before any disk transfer starts.

- On reload, the data climbs disk to host first. GPU memory is allocated only after the data has landed in host, a rule the article names just-in-time allocation.

The copies themselves run through cudaMemcpyAsync alongside model computation, so the transfer overlaps useful work instead of displacing it. Both directions stage in host DRAM. So a storage tier at NVMe latency adds time to a miss without taking GPU blocks hostage.

GPU HBM: freed when DMA copy ends

CPU DRAM: the staging point

NVMe tier

spill: async DMA

reload lands in host first
then GPU allocated

The two transfer rules: spill frees the GPU block on DMA completion, and reload allocates it only after the data reaches host. Illustration of the design, not measured.

This is what makes the disk tier tolerable, and it has a checkable consequence on one box. A reload waiting on slow NVMe storage occupies zero GPU blocks while it waits.

Evidence
The free-on-copy-complete rule and just-in-time allocation come from the vLLM blog of 2026-09-10. The cudaMemcpyAsync behaviour comes from the official usage guide at tag v0.26.0. The 200 millisecond NVMe figure is illustrative, not measured.

You can see this on your own setup. Enable the default CPUOffloadingSpec on a single box with one --kv-transfer-config. Send a long prompt twice, and watch free memory in nvidia-smi during the second request. It should stay flat until the host copy lands, then drop.

All KV moves through host DRAM, so the GPU holds blocks only while data sits in them.

The belief that a slow tier reserves GPU memory while loading makes you size HBM for it.

Enable CPUOffloadingSpec on one box and watch nvidia-smi free memory during a long-prompt reload.

This section explained one server's transfers, but a disk tier pays most when several replicas share it. The next section answers how they share one cache without talking to each other.

## How two servers share one cache without talking to each other

Sections one and two gave one server a spill path from GPU to disk. With two replicas behind your router, a prefix cached on replica A is still a recompute on replica B.

Predict: two users on two replicas send the same 12,288-token system prompt, and each replica spills to its own disk. Does the second request get a hit?
On private disks it does not, because replica B's disk holds nothing replica A wrote. On one shared mount the answer flips to yes, and the reason is how chunks are named.

The filesystem tier names each chunk by the hash of its token sequence, a scheme called content addressing. The name comes from the content, never the server, so the same prefix from any user or replica lands on one filename. A lookup is one hash and one file check, and servers never talk to each other.

replica A
user 1's prefix

replica B
user 2's same prefix

-

-
store
lookup

shared NVMe mount
9f3a…c1.kv = hash(tokens 1 to 12,288)
written once, read by both

One prefix, one filename, however many replicas write it. Illustration of the naming scheme, not measured.

- On store, the tier hashes the chunk's token sequence, and that hash is the filename.

- The host layout ignores run configuration, so the authors state a TP=2 node and a TP=4 node produce byte-identical chunks for the same KV.

- On lookup, the replica hashes the incoming prefix and checks one path, and a hit is a plain file read.

One seed splits the cache. The v0.26.0 docs require one fixed PYTHONHASHSEED, for example "0", on every instance. Without it, identical content writes different files, cross-replica hits stay at zero, and nothing logs why.

### Cache-aware routing keeps hits off the disk

A shared mount still pays an NVMe read on each first hit. The framework emits events about which instance holds which chunks. A cache-aware router such as llm-d then steers each request to the instance that already holds the prefix in faster memory. The shared disk is the floor under that.

Evidence
The layout and naming are from the vLLM blog of 2026-09-10, and byte-identity across TP sizes is author-stated and unconfirmed, though the docs' config digest is consistent. PYTHONHASHSEED and the "0" example are verified in the usage guide at tag v0.26.0. Ray's production docs independently confirm cache-aware routing.

Open the v0.26.0 usage guide, find the PYTHONHASHSEED line, and add it to your deployment checklist beside the other replica environment variables.

A chunk's filename is its token hash, so one shared mount serves every replica.

One unset PYTHONHASHSEED and identical content hashes differently, so replicas silently share nothing.

Grep the v0.26.0 usage guide for PYTHONHASHSEED and add it to your replica checklist.

This section assumed shared hits are worth having. The next section answers when offloading is a tax instead of a win.

## When offloading is a tax instead of a win

The first three sections showed the tiered KV cache working. None of them said when it should not be switched on.

Offloading costs money on every request that finds nothing in the lower tiers. Ray's production docs report that on cache misses, offloading adds roughly 10 to 15 percent overhead versus pure GPU caching. A miss means the spill copies, the lookups and the hash work all ran for nothing.

Predict: two services see 200 requests each day. One is your multi-turn chat, twelve conversations of 12,288 tokens. The other is 200 unrelated one-shot prompts. Offloading is switched on for both. Which service gets slower?
The one-shot service. Every request both pays the offload copy and misses every tier, so it runs 10 to 15 percent slower for no gain. The chat service's later turns hit the CPU or disk tier, and one hit from NVMe beats recomputing 12,288 tokens, so it wins overall. The deciding property is how often two requests share a prefix.

Evidence
The 10 to 15 percent miss overhead is from Ray's Serve LLM guide, named there as per internal experiments. The hit-beats-recompute comparison rests on vLLM's own benchmark and LMCache's independent TTFT measurement (cold 6.314s versus warm 0.148s on Llama-3.1-8B, single request).

The decision rule follows directly. Measure your prefix-reuse rate first. Multi-turn sessions, agent retry loops and shared system prompts reuse prefixes, so offloading pays. One-shot traffic reuses nothing, so offloading is pure cost. If your requests rarely share prefixes, leave the feature off.

### The defaults that shape an offload config

When reuse is real and you do switch it on, three defaults from the v0.26.0 usage guide decide what your tiers hold.

- offload_prompt_only defaults to true, so only prefill blocks are offloaded and decode blocks are skipped.

- eviction_policy defaults to lru, with arc as the alternative.

- The CPU tier is sized by one total across all workers, not per worker, and the docs warn that a CPU tier smaller than the aggregate GPU KV cache merely mirrors the GPU and adds no hit rate.

In the running case the CPU tier was set to 147GB, about twice the GPU KV cache size, which is how it carried conversations 65 through 128 instead of duplicating what HBM already held.

Offloading pays only when prefixes repeat; on misses it costs 10 to 15 percent.

Switching it on for one-shot traffic makes every request slower and gains nothing.

Open the v0.26.0 usage guide and find offload_prompt_only, eviction_policy and cpu_bytes_to_use before writing any config.

You can now decide when offloading pays and size its CPU tier. The lab below builds the full five-line config for a filesystem tier.

## Lab: fifteen minutes with the offloading config

-  L1 offline
Open the vLLM usage guide at tag v0.26.0: https://raw.githubusercontent.com/vllm-project/vllm/v0.26.0/docs/features/kv_offloading_usage.md. Find the TieringOffloadingSpec table and the secondary_tiers list, then write out the five lines of config that add a filesystem tier to a single-box server. Your finished config should take this shape:
--kv-transfer-config '{
  "kv_connector": "OffloadingConnector",
  "kv_role": "kv_both",
  "kv_connector_extra_config": {
    "spec_name": "TieringOffloadingSpec",
    "cpu_bytes_to_use": ...,
    "secondary_tiers": [ { "...": "fill in from the doc" } ]
  }
}'

Two checks while you write it: what does the doc say about PYTHONHASHSEED, and why does cpu_bytes_to_use being a total across workers matter on a 2-GPU box?

-  L2 offline
Size the tiers for the lesson's running case. One conversation's first turn is 12,288 tokens. Estimate KV at roughly 0.5 MB per token from your own model's head count and head dimension.
KV per conversation = 12,288 tokens x 0.5 MB/token ≈ 6.1 GB
CPU tier            = 147 GB                      (the blog's setting)
147 / 6.1           ≈ 24 full conversations
GPU KV budget       = about 74 GB, the blog used CPU ≈ 2x GPU
74 / 6.1            ≈ 12 conversations on HBM alone

The CPU tier doubles what fits, but a later round adds 4,096 tokens per conversation, about 2 GB each. At what round does the 147 GB tier fill up?

-  L3 offline
Check the defaults you are accepting before you would run this. confirm offload_prompt_only=true and eviction_policy=lru in the doc, then decide whether the CPU tier you sized in L2 passes the sizing rule from the last section: larger than the aggregate GPU KV cache.

You now have the config lines and the two numbers that decide whether this feature pays. The checkpoint puts them to work on a failure scenario with your own replicas.

## Checkpoint

You run two vLLM replicas behind a router for your multi-agent system. Each agent session keeps a long history, so every new turn re-reads the whole conversation as a prefix. Traffic doubles overnight, and p99 TTFT, the time from sending a request to the first token, doubles with it. The GPU KV cache metric reads full. Each box has spare host RAM and an NVMe disk available.

- Which tier do you add first: the CPU tier or the filesystem tier, and why?

- Your sizing rule says the CPU tier must be larger than the aggregate GPU KV cache. Each box has 74 GB of GPU KV across 2 GPUs. Does 128 GB of host RAM per box pass?

- After the CPU tier fills, you add the filesystem tier on the spare NVMe, mounted on both boxes. What one value must match on both replicas before the two servers share a single prefix?

- A week later, which single metric tells you the change paid, and what result would tell you to switch it off?

Answer sketch

- The CPU tier first. It is the cheapest capacity to add, every byte of KV already passes through host DRAM on eviction, and it serves hits at DRAM latency instead of disk latency.

- Yes against one box, no against the fleet. 128 GB is larger than 74 GB on that box, so it adds hit rate there. The rule applies per server because each box's CPU tier only serves that box's spills.

- PYTHONHASHSEED must be pinned to the same fixed value on every instance. Without it, identical prefixes produce different filenames per process and the shared mount silently shares nothing.

- Prefix cache hit rate. Sessions share long prefixes by construction, so the hit rate should rise and TTFT should fall. If the hit rate stays low, every request pays the roughly 10-15% overhead Ray's docs report for offloading on misses, and the feature is a tax.

The two posts that follow turn this lesson's two most surprising facts into short notes he could publish.

## Two things he could post

A cache read from disk beats recompute

Most people assume a cached prefix is lost once GPU memory evicts it. The tiered KV cache says otherwise: a hit served from local NVMe is cheaper than recomputing 12,000 prompt tokens. LMCache measured cold TTFT of 6.314s against warm 0.148s, a 42.6x gap, on Llama-3.1-8B with one request. The claim works as a post because his multi-turn agent sessions re-read the whole history every round. So he is the audience.

The environment variable that silently kills cache sharing

vLLM's filesystem tier names each KV chunk by the hash of its token prefix. So replicas on a shared mount share prefixes with no coordination. But PYTHONHASHSEED must be pinned to the same value on every instance, or identical prefixes produce different filenames. Then the shared cache holds nothing. No error appears: every lookup misses. This works as a short operational note, verified in the vLLM docs at tag v0.26.0.

Evidence
The TTFT numbers come from LMCache's local storage documentation (docs.lmcache.ai). It is a project independent of vLLM, measured on Llama-3.1-8B in a single-request demo. The PYTHONHASHSEED requirement comes from the vLLM KV offloading usage guide at tag v0.26.0.

## Sources

- vLLM blog: Tiered KV Cache Offloading (2026-09-10) — the design, the host-centric routing and the benchmark. The throughput-doubling figure is author-reported only; no independent rerun exists.

- vLLM KV offloading usage guide, tag v0.26.0 — the defaults (eviction_policy=lru, offload_prompt_only=true), the PYTHONHASHSEED requirement and the sizing rule that the CPU tier must exceed the aggregate GPU KV cache.

- LMCache local storage docs — the independent TTFT measurement: 6.314s cold against 0.148s warm on Llama-3.1-8B, single request.

- Ray Serve LLM KV cache offloading guide — the counterpoint: roughly 10-15% overhead on cache misses versus pure GPU caching.
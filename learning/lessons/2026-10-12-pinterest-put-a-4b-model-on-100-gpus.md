Across the serving phases you built an inference stack piece by piece: continuous batching, chunked prefill, prefix caching and KV-aware routing, each shown to work on a small synthetic workload. What those phases could not tell you is which piece carries the weight on a real workload, because a synthetic one is shaped to show one mechanism at a time.

On 2026-10-09 Pinterest published a real account: a 4B model regenerating an intent profile for each of hundreds of millions of users, one activity log in and a short JSON list out, serving about 775 requests a second on about 100 GPUs. After this lesson you can say which mechanism that number rests on, and predict from a workload's shape whether keeping earlier computation around will help it at all.

This lesson teaches one idea. It is stated here so you can see where the lesson is going. It will read more clearly once it has been explained below, so come back to it at the end.

- Prefix caching reuses the key-value tensors of an identical token prefix, so it removes only the prefill compute of that prefix and cannot touch decode. Say which phase of any request a prefix cache acts on, and where the remaining latency must come from.

## What did Pinterest actually build, and which piece carries the number?

Predict: when a user's request reuses a stored computation, how much of its prefill does the GPU skip: all of it, half of it, or only the activity log's share?
Only the activity log's share. The shared prompt's prefill was computed once and stored, so each new request skips it. The log is new for each request, because every user's log differs, so the GPU computes that part every time.

Here is the system Pinterest runs. A fine-tuned Qwen3-4B reads one user's profile and up to 150 activity events over 360 days. It emits a short JSON list of that user's journeys. It does this once per user across hundreds of millions of users.

Serving happens on the stack you read about in the serving phases, with a router in front. NVIDIA's Dynamo receives requests and routes them to vLLM workers on about 100 L40S GPUs. To see why this workload is cheap, you need the two phases every request passes through.

- The prefill is the single pass that processes the whole prompt in parallel, before any output token exists. Its compute grows with prompt length.

- The decode is the loop that produces output one token at a time. Each token needs its own step, so a long answer costs many steps regardless of prompt length.

During both phases the GPU relies on the KV cache, the attention keys and values it keeps for each token it has processed. Keeping them means a token's history is never recomputed. The cache is also the memory budget that limits how many requests run at once.

The workers run continuous batching, the scheduler where a finished request leaves the batch and a new one joins on every decode step, so the GPUs never wait for a fixed batch to finish. A companion practice, chunked prefill, splits a long prefill across several steps so the running batch's decodes are not stalled by one large prompt. Together these keep the GPUs busy at roughly 775 requests a second with a 1.2 second median response (Pinterest's own numbers, unconfirmed).

Dynamorouter

-
prefill: one passshared policy prompt+ this user's 150 events

-
decode: one token per stepJSON list, ≤300 tokenstemperature 0
KV cache written hereKV cache read and extended here

The path of one request. Illustration from the article's architecture, not measured.

Two workload facts decide which phase matters:

- Every request carries the same long policy prompt, holding the ranking rules, the dislike-suppression rule and the empty-output rule.

- Outputs are capped at 300 tokens at temperature 0, so decode stays short and deterministic.

A long repeated prefix and a short output describe a prefill-dominated workload. Whether that is why 775 requests a second was reachable is the next question.

Evidence
System and numbers (Qwen3-4B, Dynamo routing to vLLM on L40S, 150 events over 360 days, 300-token cap, 775 rps, 1.2s median, ~100 GPUs) from the Pinterest Engineering article, 2026-10-09; all serving numbers are Pinterest's own with no independent check. The article also lists PagedAttention, automatic prefix caching and KV-cache-aware routing on the workers; the next section explains the caching piece. Qwen3-4B's size is confirmed by its model card.

Every request pays twice: one prefill pass over the prompt, then one decode step per output token.

Treating "serving a request" as one cost hides which phase a workload actually spends on.

For one call in your system, write the prompt length and typical output length side by side.

This section named the two phases but not which one a cache can act on. The next section answers that: why does prefix caching pay here and not everywhere?

## Why does prefix caching pay here and not everywhere?

Prefix caching pays only when long shared prefixes exist and generation is short.

The pieces above are on the table, but none of them yet explains the 775 requests per second. That number traces to one mechanism meeting one workload property.

Every Pinterest request has the same shape. One long policy prompt, the ranking rules and the dislike-suppression rule, then one user's activity log. Prefix caching keeps the KV cache of a prompt it has already processed, so the next request with the same prefix skips that work. The KV cache is the attention keys and values the GPU computes for each token during prefill, the single pass over the whole prompt before any output exists.

Predict: the shared prompt's KV entries are stored, and each reply is at most 300 new tokens. Which tokens' KV values can the cache reuse, and which do not exist yet?
The shared policy prompt's values can be reused, because prefill computed them once and stored them. The 300 output tokens' values cannot, because they are only computed as decode generates each token. Nothing is stored for tokens that do not exist yet, so the cache can never act on decode.

Walk one request through the system:

- The request arrives carrying the shared policy prompt plus one user's log.

- vLLM matches the prompt's tokens against stored blocks and finds the whole policy prompt already cached, because hundreds of earlier requests carried it.

- Prefill runs only over the user's activity log, the small new part, and reuses the stored KV entries for everything before it.

- Decode then generates the JSON list one token at a time, computing fresh KV values for each token it produces.

Step 4 is the boundary. The KV values of the generated tokens do not exist until decode produces them, so no cache can store them ahead of time. Prefix caching removes shared prefill compute and nothing else.

That is why the workload's shape decides everything. Pinterest is a prefill-dominated workload, one where processing the prompt costs more than generating the answer. Its prompt is thousands of shared tokens and its output is capped at 300. Remove most of the prefill and most of the cost goes with it. A chat workload inverts this: a short unique prompt, a long answer, and the cache barely moves anything.

Pinterest: long shared prefill, short decode

prefill — shared, cacheable
decode
Chat: short unique prefill, long decode

decode — the cache cannot touch this
Illustration of the two workload shapes, not measured. The cacheable share is large only in the first bar.

vLLM's own documentation states this limit directly.

Evidence
From the vLLM Automatic Prefix Caching documentation: "APC only reduces the time of processing the queries (the prefilling phase) and does not reduce the time of generating new tokens … no performance gain when vLLM spends most of the time generating answers … or new queries do not share the same prefix". The 775 rps and latency figures are Pinterest's own numbers with no independent check (unconfirmed).

So before you enable prefix caching on your own stack, check two things. Count how many prompt tokens are identical across requests, and compare the shared prefix length against the average output length. If answers run longer than the shared prefix, decode dominates and the cache will not move your latency.

Prefix caching deletes shared prefill work and leaves every generated token at full price.

Thinking a cache speeds up the whole request wastes effort when decode is where your time goes.

For one call you run, compare shared prompt tokens against output tokens and name the larger one.

Prefix caching explains why each request is cheap, but the total cost also depends on how many requests run at all. The next section answers what Pinterest did that was cheaper than any GPU change.

## What was cheaper than any GPU change?

Pinterest's largest saving came from requests that never reached a GPU at all.

Prefix caching explains why each request is cheap. How many requests run at all is a separate decision, and it sets the total cost.

A journey built from 360 days of activity barely changes overnight, so re-deriving it tomorrow buys nothing and costs a full inference. Pinterest's answer is the last-inferred skip, one timestamp per user. The scheduler records when each user's journey last ran, and it does not send that user to the model again within the next couple of days.

Predict: Pinterest sustains about 775 requests per second. If 200 million users each ran the model once, how long would one full sweep take?
# 200,000,000 users, the low end of "hundreds of millions"
200,000,000 ÷ 775 requests per second ≈ 258,000 seconds
258,000 seconds ÷ 3,600 seconds per hour ≈ 72 hours ≈ 3 days

Even at full speed day and night, one sweep takes about three days, so running everyone daily cannot fit on this fleet. The system keeps up because the skip removes most users from most sweeps. Both figures are Pinterest's own (unconfirmed), but the conclusion holds at any user count.

The skip lives in the scheduler, before any serving machinery gets a turn:

- A finished inference writes its completion time onto the user's record.

- The next sweep reads that timestamp before building a prompt, so the check costs less than the work it avoids.

- A user inside the window is dropped from the sweep and costs no GPU time, no queue time and no tokens.

- Only users outside the window get a prompt and join the queues from the serving phases.

- Was this user's journey inferred within the last couple of days?

- yesskip the user, no prompt built, no GPU touched

- nobuild the prompt and run the full stack

The failure this avoids never looks like an error. Latency stays low, the GPUs stay busy and every answer is valid, because re-deriving an unchanged journey still produces a journey. Pinterest calls this the most expensive kind of waste. So the rule lands before any server tuning. Count the requests that did not need to run, and graph the skipped count next to latency.

Evidence
From the Pinterest Engineering article of 2026-10-09: "we track when each user was last inferred and skip anyone processed within the last couple of days." The article reports no skip rate, so the share of users removed from each sweep is unknown.

### Three habits that keep the remaining runs cheap

Three smaller habits set the cost of the requests that remain.

- Bounded concurrency per shard. The fan-out splits users into shards, and each shard, one slice of the list, caps its in-flight requests. A slow decode then stalls one shard instead of the whole sweep.

- Retry the whole user. A failed decode discards the partial list and re-runs the user. Storing half a profile corrupts it, and the retry pays little prefill because the shared prompt stays cached.

- An empty list is a valid answer. The prompt allows empty output, so an empty JSON list is stored as a success instead of retried on every sweep.

The cheapest request is the one a scheduler decides not to run.

Re-running unchanged inputs looks like progress on a dashboard while the fleet pays.

Count yesterday's calls that repeated an unchanged input, and write down the share.

When you re-read the serving phases, read each optimisation as an act on one phase of the request, not as a general speedup. Prefix caching removes shared prefill work and leaves decode untouched, and the cheapest request is the one a scheduler decides not to run. The lab checks both on one call of your own system.

## Try it on your own stack

You have seen both checks on Pinterest's workload. The shared-prefix test is for prefix caching, and the last-inferred test is for skipping requests. Now run the same two tests on one call in your own system. Fifteen minutes is enough.

-  T1 offline Pick one LLM call in your multi-agent system, for example the prompt your planner agent receives. Count the identical prefix: run two real requests, write each prompt to a file, and diff them. Note how many tokens before the first differing byte are the same across requests. This is the part prefix caching could reuse.

-  T2 offline Measure the output length: average the completion tokens over twenty real responses, or read the cap you set on the call. Compare this with the shared prefix from T1.

-  T3 offline Count the repeats: log a hash of each full input for one day, then count how many hashes appear more than once within a few hours. Each repeat is a request a last_inferred timestamp could have skipped.

Then apply the two rules from this lesson.

Prefix caching will not pay when the average output is longer than the shared prefix. vLLM's docs state the cache acts only on prefill, so when decode takes most of the time, a cache hit barely moves latency.

Prefix caching pays when one long prompt repeats across requests and outputs stay short: the prefill of the shared prefix runs once and every later request reuses its KV entries.

The third number answers a different question. If T3 shows the same input returning within hours, the first fix is a timestamp and a skip check. No serving optimisation beats a request that never runs. If T3 shows every input is unique, caching and skipping both stay off the table. Your cost then sits in decode.

Evidence
The prefill-only limit of automatic prefix caching comes from the vLLM documentation, read 2026-10-12. The skip rule is Pinterest's own description: they record when each user was last inferred and skip anyone processed within the last couple of days. No independent check of the serving numbers exists.

Sentence one of the checkpoint replays this. It is one workload from your own system, and the question of whether prefix caching will help it.

## Checkpoint

The lab showed how to measure one workload. This scenario asks you to make the call before running anything.

Your multi-agent system gives every agent the same 4,000-token system prompt, and each answer runs about 1,500 tokens. Latency is rising as you add agents. A colleague suggests turning on prefix caching because every request shares that long prompt. Pinterest's article made the same setup look like a clear win.

- Should prefix caching help much here? Use the limit from vLLM's documentation to answer.

- What single measurement would you take first to check your answer, before turning anything on?

Answer sketch
1. Probably not much. The vLLM documentation says automatic prefix caching acts only on prefill and cannot touch the generation of new tokens. A cached hit would remove the prefill of the 4,000-token prefix, but every request still decodes 1,500 tokens of output. Decode produces one token at a time, so for most models 1,500 decode steps dominate the 4,000-token prefill's single pass. The cache removes the smaller half of the latency. This is the opposite of Pinterest's case, where outputs were capped at 300 tokens and the shared prefix was long.

2. Measure the prefill versus decode share per request first. Split each request's latency into time to first token (prefill plus queueing) and the remaining streaming time (decode). If decode takes most of the request, caching will not pay. Then the colleague's proposal no longer needs answering by hardware. If prefill shows up larger than you expected, then the 4,000-token shared prompt is the workload shape. Prefix caching was made for it. One number decides the whole argument.

Note the trap Pinterest's article sets. It described the same visible setup, one long shared prompt, and got a large win. The difference is invisible in the prompt. It sits in the output length, so it sits in the decode phase that no prefix cache can act on.

If both calls felt obvious, the lesson did its job. You now read every serving optimisation as an act on one phase of one request. The next question writes itself.

## What he could post

Two posts this lesson can become, each a claim only someone who read the mechanism can make.

- Prefix caching cannot speed up a single output token. The vLLM documentation says it plainly: automatic prefix caching acts on prefill only, and it does nothing when the workload is decode-heavy or shares no prefix. Yours is the two-bar picture drawn from your own workload: prefill and decode side by side, the cache shading only the prefill half. Pinterest's 300-token cap and long shared prompt sit on the winning side; a decode-heavy load sits on the losing side.

- The cheapest request is the one the scheduler refuses to run. Pinterest tracked each user's last-inferred time and skipped anyone processed within a couple of days, and that save outranked every GPU change. Yours is the general pattern: count requests skipped as a serving metric next to latency, because work that never reaches the GPU is the only work with a zero bill. What makes it yours is that you read it as scheduling, not as infrastructure.

## Sources

Everything in this lesson traces to these. The serving and A/B numbers are Pinterest's own, with no independent check.

- From Activity to Intent: Generating User Journeys with LLMs, Pinterest Engineering, 2026-10-09. The running case: the workload shape, the stack, the skip rule, and all the serving numbers. Read in full through Medium's publication RSS feed, because the page itself refused plain fetches.

- vLLM Automatic Prefix Caching documentation. The mechanism's hard limit: it reduces prefill time only, never decode time, and pays nothing when requests share no prefix.

- Qwen3-4B model card. Confirms the student model exists as described: 4.0B parameters, 36 layers, 32,768-token context, Apache 2.0. The greedy-decoding warning applies to thinking mode, which Pinterest disables.

- LIMA: Less Is More for Alignment, Zhou et al. 2023. Independent confirmation that alignment quality saturates with a few thousand curated examples.

- TIGER: Recommender Systems with Generative Retrieval, Rajput et al., NeurIPS 2023. The origin of the semantic-ID mechanism Pinterest extends.

The 775 requests per second, the 1.2-second median, the GPU count, and the A/B lifts come from Pinterest alone. No ablation (prefix caching on versus off, for example) is published, so treat each number as a claim, not a benchmark.
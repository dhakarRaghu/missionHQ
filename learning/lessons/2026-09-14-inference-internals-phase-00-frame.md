# Inference Internals, Phase 0: Frame the problem

## Why does one line in a prompt cost five times the bill?

You ship a support agent on top of an LLM API. The first invoice is 40 dollars. Then you notice the model keeps guessing the date wrong, so you add one line to the top of your system prompt: the current time, precise to the second. The answers get a little better. The next invoice is over 200 dollars. Traffic is the same. Code is the same. Model is the same. The provider dashboard shows about the same volume of text flowing through. So where did the money go?

Nobody could have answered that from your codebase, because the answer lives on the other side of the API. The provider remembers text it has already processed, and it gives you a discount of about 90 percent when your request starts with something it has seen before. Your timestamp changed that remembered prefix on every single request, once a second. Every request arrived as a stranger and paid full price. The line that fixed the date silenced the discount.

Here is the claim this phase builds up to. Every request you send runs through one machine, and that machine has two phases with opposite physics: one reads your whole prompt in parallel, the other writes the answer one piece at a time. Price and latency both fall out of that split. Once you can see the machine, a mystery bill stops being a mystery. It becomes a question about which stage you are paying for. The rest of this course is learning to answer that question precisely, and this phase is the frame.

## What does this phase cover?

Four things. First, what runs between your API call and the answer: the stages, and the two hardware facts that govern them. Second, the three numbers that describe the speed and cost of any request, and the one formula that joins them. Third, three failure stories, each caused by something on the application side rather than by the model. Fourth, the map of the remaining phases. There is no code in this phase. The single command at the end is setup for Phase 1.

## What happens after your request leaves your code?

Start from what you can observe with no internals at all. Stream one request and watch the screen: nothing for a while, then text in chunks at an almost even pace. Two timings are visible from your side alone: the wait before the first chunk, and the spacing between chunks after that. The machine explains exactly that pattern.

Here is the path. Your prompt arrives as a string. A tokenizer splits it into tokens, the chunks of text the model actually reads. A token is roughly three quarters of a word, so a 7,500-word document is about 10,000 tokens. The request then joins a queue, because the provider's GPUs are shared and you wait your turn. Then the whole prompt is processed in one pass. That pass is called prefill. After prefill, a loop starts: the model computes probabilities for the next token, picks one by sampling from those probabilities, appends it to the text, and repeats, one token per step. That loop is decode. Each token is streamed back to you the moment it exists. So the full path is: tokenize, queue, prefill, decode with sampling inside it, stream.

Two consequences before any math. The model reads your entire prompt before it writes anything; there is no partial reading. And the answer's length decides how many times the loop runs. That is why a long answer feels slow in a way a long prompt does not, and the next section shows why the gap is so large.

## Why is reading parallel but writing serial?

Time those two visible numbers on a big prompt. Send 10,000 input tokens and the wait before the first token might be about 2.4 seconds. The spacing between later tokens is maybe 50 milliseconds. Read the naive way, the machine consumed your prompt hundreds of times faster than it writes. That asymmetry is not a tuning decision by the provider. It is physics, and it is where the useful mental model lives.

The two hardware facts. Prefill is compute-bound: the processing of each input token is independent matrix multiplication, so the GPU runs thousands of tokens of arithmetic side by side, and the limit is raw compute, measured in FLOP/s (floating point operations per second). Decode is memory-bandwidth-bound: each output token depends on every token before it, so the steps cannot run in parallel, and in each step the GPU does little math but must load the full model weights from memory. The limit there is memory bandwidth, bytes per second.

The crossover point falls out of the specs. On an A100 GPU, 312e12 FLOP/s divided by 1.5e12 bytes per second gives about 208: reading up to roughly 208 tokens costs the same wall-clock time as writing one. That arithmetic is from kipply's *Transformer Inference Arithmetic* (March 2022), and the post checks it against hardware: a 13-billion-parameter model on one A100 took 22.0 milliseconds per decode step where the formula predicted 16.8 to 22. Real bandwidth is about 90 percent of the rated number, which pushes the practical crossover to roughly 231. So 10,000 input tokens cost about the time of 48 output tokens: 10,000 divided by 208 is about 48 steps. The module's rough figure of about 40 is a little low. On an H100 the ratio moves to around 295, but note that this is my arithmetic from published specs (990 TFLOP/s against 3.35 TB/s), not a measured figure.

One honest caveat: at very small batch sizes a server can be memory-bound even during prefill, and can prefer recomputing history over storing it. The parallel-read, serial-write picture is the right first model. The exceptions live in Phase 2's material on batching.

## What does the GPU remember while it writes?

Run the serial loop as a thought experiment. To produce token 51, the model attends over tokens 1 to 50. To produce token 52, it attends over 1 to 51. If step 52 recomputed all of that from scratch, every new token would cost a full re-read of the growing history. Use this phase's numbers: one 50-millisecond step per 208 tokens read. With a short prompt, a 1,000-token answer would re-read about 500,000 tokens in total. That is about 2,400 steps, or about 2 minutes instead of 50 seconds. With a 15,000-token prompt, every step re-reads at least 15,000 tokens, and the same answer takes about an hour. That does not happen, because the GPU keeps per-token vectors, called keys and values, in its memory. That stored history is the KV cache: the attention keys and values the GPU holds onto so it never has to recompute the past. Phase 1 does the byte-level math of how large it gets. This phase only needs what it buys.

What it buys explains four things you already pay for. A long conversation keeps growing the cache until the GPU runs out of room for other customers, which is why concurrency limits exist. Re-sending a long history on every agent step is mostly re-using stored work, which is why providers can discount repeated input. And the cache is the reason the cheapest lever in this entire course exists at all, which is next.

## Why can the same prompt be billed ten times cheaper?

The behaviour first. Send a request with a large, fixed system prompt. A minute later, send the identical request. On the second call the provider recognizes that it already ran prefill over that exact text, skips most of the reading work, and bills the repeated input at about a tenth of the normal input price. This is prefix caching: the provider keeps the prefill result of a repeated starting chunk and reuses it across requests.

The condition is strict: the prefix must match byte for byte. OpenAI's documentation lists what counts as part of it: hidden system content, developer messages, tool definitions, schemas, everything the server rendered before your text. A team that tested its production agent across millions of users (the failure story below) puts the operating version plainly: even a single-token difference can invalidate the cache from that token onward. So the rule of thumb for this course is: static content first, variable content last. Keep the front of your prompt stable and the discount stays alive.

## Why do output tokens cost five times input tokens?

Price follows the physics. Input tokens are processed thousands at a time against a compute budget. Output tokens are processed one at a time against a bandwidth budget, and each one occupies a GPU step alone. That is why every bill has two columns, and why the output column is the expensive one. The module cites a 3x to 8x range across providers, with gpt-4.1 pinned at $2 per million input tokens against $8 per million output on 2026-09-01, a 4x ratio.

The current market, checked 2026-09-13, sits at 5x to 6x: gpt-6-astra at $10/$50, gpt-5.6-sol at $4/$20, gpt-5.6-luna at $0.20/$1.20, and Anthropic's Claude Sonnet at $3 in against $15 out. The older example's date pin is doing its job: gpt-4.1 no longer appears on the front pricing page, so treat that pair as era-accurate rather than current. There is a real consequence of that drift later in this lesson.

## What three numbers describe any request?

Any request, any provider, any model: TTFT, TPOT, and dollars per million tokens. Time to first token (TTFT) is the queue wait plus prefill. It scales with your prompt length and with how loaded the provider is, so it is mostly your prompt's fault. Time per output token (TPOT) is the decode step time. It scales with model size and provider load, and with nothing you sent, so it is the provider's GPU's fault. The third number is the end-to-end cost per million tokens, read off the invoice, because the first two never tell you what a month of traffic costs.

The module claims almost no agent stacks record the first two numbers. That matches how these systems usually get built, but it comes with no survey behind it, so treat it as a claim to test on your own telemetry rather than as literature. Your stack logs tokens and cost per call. Whether it logs the wait before the first token is worth checking, and the setup block at the end is exactly that check.

## Can one formula predict every slow request?

One formula covers most user complaints: **total time = TTFT + output tokens × TPOT**. Its power is that the same latency can land on either side of the plus sign, and the fix is different on each side.

Use the crossover numbers from earlier: TPOT of 100 milliseconds, a typical queue of 0.3 seconds, and prefill costing one decode step per 208 tokens. Request A: a 20,000-token prompt, so prefill is about 96 step-times, or 9.6 seconds; TTFT lands near 10 seconds; 10 output tokens add 1 second. Total: about 11 seconds. The fix is a shorter prompt or a cached prefix. Request B: a 200-token prompt, so TTFT is under half a second; 107 output tokens take 10.7 seconds. Total: about 11 seconds. The fix is fewer output tokens or a faster model. Two dashboards, both showing 11-second requests, and the fix that helps one makes the other no better. Decompose the number before you tune anything.

## What can the formula not see?

The formula prices a request as one input number plus one output number. Reality has more columns, and in 2026 more columns than the module knew when it was written. Cached input is its own cheaper rate. Batch APIs trade latency for discounts. Reasoning models generate hidden tokens that are billed as output before the visible answer starts.

The newest column is the cache's write side. On OpenAI's GPT-5.6 and newer models, writing a prompt into the cache costs 1.25 times the uncached input rate; reading it back costs 0.1. Anthropic's documentation, which Phase 1's reading list already cites, charges 1.25x to 2x on writes and 0.1x on reads. A hit is also best effort, never promised: the cache is machine-local, not shared across organizations, and not guaranteed across regions, and the minimum cacheable prefix on OpenAI is 1,024 tokens. So a constantly rewritten prompt on a write-billed model can cost more than no cache at all. The module's simple picture, a hit is 0.1x and a miss is 1x, was right when written. The miss case is the correction: a miss can be 1x on older models, 1.25x on current ones.

## Failure story 1: how did a timestamp kill a cache?

Prefix caching means a provider keeps the result of processing a repeated starting chunk of a prompt and bills reads of it at about a tenth of the input price. The catch is that the chunk must match byte for byte. That single mechanism produced one of the best-documented production failures in this space.

In July 2025, Yichao 'Peak' Ji, the chief scientist of the agent company Manus, published what his team learned from testing an agent across millions of users. He calls one mistake common: putting a timestamp, especially one precise to the second, at the beginning of the system prompt. The model gets grounded in time, and the cache hit rate dies, because the first token of the prompt changes every second and everything after it misses forever. His numbers make the cost concrete. Claude Sonnet reads input at $3 per million tokens and reads cached input at $0.30. Manus's agent traffic averages about 100 input tokens for every 1 output token, which is what agent loops do: every step resends the instructions, the tool definitions, and the full history. Input is about 99 percent of the tokens, and most of that input repeats the step before. With a working cache, the repeated part bills at a tenth of the input price. With a timestamp on top, every step pays full price for all of it. Here is where five times comes from. Take one step of 100 input tokens and 1 output token at these prices, in dollars per million tokens. With every input token cached, the step costs 100 × 0.30 + 15 = 45. With the cache broken, it costs 100 × 3 + 15 = 315. That is 7 times, the upper bound. A cache that hit 93.3 percent of input before the break costs 100 × (0.933 × 0.30 + 0.067 × 3) + 15 = 63, and 315 is 5 times 63. So the jump from 40 dollars to over 200 dollars fits a hit rate a little above 93 percent.

The same post names a second killer the module does not have: JSON serialization with unstable key ordering. If your framework serializes a dictionary whose key order changes between runs, the bytes of your prompt differ request to request, and the cache is invalid from the first differing token onward. The post's operating rule is the one to keep: the KV-cache hit rate is the single most important metric for a production-stage AI agent. The price of learning it: Manus rebuilt its agent framework four times.

## Failure story 2: why do retries make an outage worse?

The provider's queue stalls: requests hang, or come back with rate-limit errors. Your client retries at once. So does every other client pointed at the same API. Now the provider is not carrying the original load; it is carrying the original load plus every retry, from every customer, timed to land together.

The mechanism here is older than LLMs and is documented at AWS scale. Marc Brooker's simulations on the AWS Architecture Blog show the shape: when N clients contend for a bottleneck, completion time grows linearly in N, but total work in the system grows with N squared. Retries are what inject the extra N. Plain exponential backoff alone does not save you, because uncorrelated clients back off to the same schedule and their retries synchronize into clusters that land together; adding random jitter to each delay is what breaks the clusters up. Be honest about the evidence here: no public postmortem of an LLM-API retry storm has surfaced. Story 2 is a classic cloud failure mode applied to a queue with the same shape, so treat it as a mechanism to defend against, not a war story someone else paid for. The defence: cap retries, back off exponentially, and add jitter, in that order.

## Failure story 3: why is a model swap a silent code change?

A model name sits in one config line. Someone bumps it from the current model to the new one, globally, because the new one is better on a leaderboard. Nothing crashes. The agent still answers. But the tone changed, a tool-calling edge case regressed, and the retry rate on one step quietly doubled. Because nothing errored, nothing in the alerting sees it, and because the change was one line, nobody connects the new behaviour to it for a week. The module presents this as an archetype, not a sourced incident, and the honest reading is that every model change is a code change with no diff to review unless you build the review yourself: a fixed eval set, run on every swap, before the swap ships.

There is a concrete, dated instance of this arriving at you whether you act or not. OpenAI's deprecations page lists a shutdown batch on 2026-10-23 covering gpt-4 variants, gpt-3.5-turbo-0125, gpt-4o-2024-05-13, o1, and o3-mini. Whether the gpt-4.1 family is inside "gpt-4 variants" is not confirmed in what we could read; check the page yourself before running the October labs. If your lab default model retires, a swap is forced on you. The eval gate is what keeps it from being silent.

## Where does the course go from here?

This phase drew the frame. The rest of the course fills it in. Phase 1 opens the KV cache properly: the byte-level size math, what keys and values actually are, the exact mechanics of when a prefix match breaks, and how to read the usage fields on a response. Phase 2 goes inside the serving engine: batching, and the scheduling tricks that make many users share one GPU. The later phases move up the stack into measurement, cost engineering, and operations. Throughout, the course pins prices in a `prices.yaml` file dated 2026-09-01, so the numbers stay honest even as price pages drift, and every lab can run against any OpenAI-compatible endpoint by pointing `--base-url` at it.

## What changed since this module was written?

Three plain corrections. One: the 90 percent cache discount is the read side only. Current OpenAI models bill cache writes at 1.25x the input price, so a prompt that never hits can cost more than no cache. Two: the module's gpt-4.1 price example is dated 2026-09-01 and could not be re-verified on 2026-09-13, because the model has left the front pricing page; the shutdown batch on 2026-10-23 may or may not include it, so check the deprecations page before the Phase 1 labs. Three: the retry-amplifies-congestion story rests on the AWS contention result, not on an LLM-specific public postmortem, because none was found; and the H100 crossover of about 295 is spec arithmetic, not a measurement.

## What should you set up before Phase 1?

This phase has no lab and no code, by design. Three five-minute things, and Phase 1 starts immediately runnable. First, put your key in place: `export OPENAI_API_KEY=sk-...` in the shell you will use for labs. Second, open your provider's deprecations page and check whether the model pinned in `prices.yaml` survives past 2026-10-23. Third, open your own agent's telemetry and answer one question: per API call, do you log how long the first token took, or only token counts and cost? If only counts, you have the bill but not the machine. That gap is Checkpoint question 7.

## Checkpoint 0: answer in your own words

1. In your own words, why does the first token of a large prompt arrive after one big wait instead of trickling in slowly?
2. Your prompt is 20,000 tokens and the answer is 10 tokens. Which side of `total = TTFT + out × TPOT` dominates, and what are the two levers?
3. What exactly must match for a prefix cache to hit, and name two innocent-looking changes that break it.
4. Name three things the two-column price formula cannot represent in 2026 pricing.
5. Both example requests took about 11 seconds. Why did they need opposite fixes?
6. Your agent resends its full history every step, about 100 input tokens per output token. With cache reads at 0.1x, roughly what happens to your input bill when the cache works, and what single change to your prompt would destroy that?
7. Before you ever blame the provider for a slow request, what one thing should your own stack be recording?

## Reference card

- The path: tokenize, queue, prefill, decode (sample each step), stream.
- The physics: prefill is parallel and compute-bound; decode is serial and memory-bandwidth-bound. Crossover on an A100: about 208 tokens of reading equal one step of writing (312e12 FLOP/s over 1.5e12 bytes/s, kipply 2022; about 231 at real bandwidth; H100 roughly 295, spec-derived).
- The three numbers: TTFT = queue + prefill (your prompt's fault). TPOT = decode step time (their GPU's fault). Third column: dollars per million tokens, from the invoice.
- The formula: total = TTFT + output tokens × TPOT. Same total, opposite fixes.
- Cache economics as of 2026-09-13: reads at 0.1x input price; writes at 1.25x on OpenAI GPT-5.6+ (Anthropic 1.25x to 2x); minimum prefix 1,024 tokens on OpenAI; hits are best effort, machine-local, not guaranteed.
- Pricing range, 2026: output runs 5x to 6x input (module's range: 3x to 8x).
- Deprecation watch: shutdown batch listed for 2026-10-23; verify your lab model before October.
- Phase 1 setup: `export OPENAI_API_KEY=sk-...`.
- Three lines you will get wrong. One: "a cache hit is 0.1x price" is only the read side; the write side can bill 1.25x. Two: a 10,000-token prompt is not slow; it costs about 40 to 50 decode steps, not 10,000. Three: the total latency tells you nothing to fix; the TTFT against decode split does.

## Two things you could post

1. "The prompt cache has a write side now: 1.25x on the miss, 0.1x on the hit." The 2026 pricing shape most posts about prompt caching never mention, tied to a number from your own agent's billing telemetry.
2. "One line, precise to the second, five times the bill." The Manus timestamp failure retold through the byte-identical-prefix rule, with the JSON key-ordering killer that nobody serializes on purpose. What makes it yours: you check your own prompt construction for the same two bugs.

## Sources

- This phase, your copy: https://raghu-monitoring.vercel.app/study/inference-internals-phase-00-frame
- kipply, *Transformer Inference Arithmetic* (the 208-token crossover): https://kipp.ly/transformer-inference-arithmetic/
- Manus, *Context Engineering for AI Agents* (timestamp and JSON-ordering cache failures, 100:1 traffic, hit-rate rule): https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- OpenAI docs, prompt caching: https://platform.openai.com/docs/guides/prompt-caching
- OpenAI docs, pricing: https://platform.openai.com/docs/pricing
- OpenAI docs, deprecations: https://platform.openai.com/docs/deprecations
- AWS Architecture Blog, *Exponential Backoff and Jitter* (the N-squared contention result): https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- Study digest behind this lesson: `quarantine/2026-09-14-inference-internals-phase-00-frame-study.md`

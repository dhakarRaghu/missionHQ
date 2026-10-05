Phase 2B ended with your prompt fitting its context budget and your stream no longer freezing mid-sentence. Your Phase 1 meter sums the input tokens and the output tokens of every response and prices them. The invoice that arrives this month matches that total on neither provider. On one provider the invoice is higher than your total. On the other, your total reads 76 percent above the invoice. No call ever returned an error.

The second clue is the line from Phase 0's first story, the current time at the top of the system prompt. Moving that one line changes the bill by more than a factor of five, and every token count stays the same. Both clues have one cause. The provider charges less for text it has processed before, and each provider reports that discount in a different place. What your usage fields actually count is the first question this phase answers. Then it answers where changing text belongs in your prompt, and when that discount is worth paying for.

This lesson teaches four ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- Usage.input_tokens means different things on different providers, so one shared summation is silently wrong by the size of your cached prefix. Write one usage adapter per provider and audit your own meter against an invoice.
- Caching is a purchase with a break-even in reads, so a workload that writes entries and reads them rarely pays more with caching on than with it off. Compute reads-to-profit from your own price sheet, pick the 5-minute or 1-hour tier, and sequence a cold-start fan-out.
- Cache hit rate is a property of your prompt layout, because the bytes that must match include tool order, output format and serializer key order, not just your text. Move volatile content out of the prefix and name every silent killer of a hit, including your own Go JSON serializer.
- Cache failure returns success with no error, so the cached-token count in the usage object is the only proof caching happened and the only signal that it stopped. Diagnose a zero cached count, and know why an error monitor will never catch this.

## Where this phase starts: a meter that matches no invoice

  The KV cache rents space, so the provider gives it back as a discount

In Phase 1 you saw that prefill is the pass that reads your whole prompt. It writes keys and values into the GPU's KV cache. This memory is the scarce thing the server rents out. When the server still holds your prompt's keys and values, it skips the prefill for them. So it charges you less for those tokens. That discount is the money this phase tracks.

  A cached prefix matches byte for byte from token 0

In Phase 2A the routing tree matched prompts from the start of the token stream. One different byte ended the match at that point. The billing cache in this phase follows the same rule. Text that changes before your stable content makes everything after it uncached, even when that later text is identical.

  Truncating from the front deletes the part that stays the same

In Phase 2B you fit an over-long conversation into the context window by cutting old messages from the front. The front was also the stable part of the prompt. So every cut moved every byte after it, and the cache never matched again. This phase prices that decision.

Those three ideas explain when work is reused. This phase is about how that reuse shows up on your invoice. It starts from the failure that frames the whole lesson. Your Phase 1 meter reads usage.input_tokens and usage.output_tokens and prices them. But it matches no invoice you receive.

The invoice is wrong in two directions at once. On one provider it is higher than your meter computes, because the meter never saw tokens that the provider bills separately. On the other it is lower. The meter charged full input price for tokens the provider billed at a tenth of that. And you added the timestamp line to the top of your system prompt in Phase 0. It moves the bill without changing a single token count. It changes which tokens the provider counts as reused.

A meter that is wrong in both directions is worse than no meter. The sections below fix it in order. First, what the five priced token classes are. Then why the same field name means two different things on the two providers. Then what in your prompt decides which class your tokens land in. Finally how to prove with one number that the discount actually happened.

## What is actually on the bill?

Your meter reads two fields, but the invoice prices five classes, so it cannot match.

You built the Phase 1 meter on one formula. Cost equals input tokens times the input price, plus output tokens times the output price. Now the invoice disagrees with that meter on both providers, and in opposite directions.

The reason is that the provider does not bill your prompt as one block of tokens. It splits the prompt by how much work the server actually did, and it prices each part differently. Your meter sees only two numbers, so it cannot express that split.

Think of one request as a row of tokens with four price labels, plus one multiplier on top. There is the plain input the server processed fresh. There is cached input, prompt tokens the server served from a stored prefix instead of recomputing them, billed at a fraction of the input price. There is cache write, tokens the server stored for later requests, billed above the input price on providers that charge for it. And there is output, billed at several times the input price.

The stored prefix is not magic. Phase 1 showed you the KV cache, the attention keys and values a server keeps for text it already processed. When your request starts with bytes the server still holds, it skips the prefill work for those tokens. The discount is how the provider passes that skipped work back to you. The fifth row, the batch multiplier, is not a token class. It is a flat discount applied to the whole request, so it multiplies every other row at once.

  One warm agent request, 11,000 tokens billed (illustration, not measured)

Predict: your audit code sums usage.input_tokens across a cached agent's turns, and the monthly invoice is several times your computed total. On which provider does this happen, and which two fields did you forget to add?
This happens on Anthropic. There, input_tokens counts only the tokens after the last cache breakpoint, so the cached tokens your agent used are missing from it. The two fields you forgot are cache_read_input_tokens and cache_creation_input_tokens. The next section opens both providers' usage objects and shows why the same field name means different things.

The mechanism is arithmetic. Your Phase 1 formula multiplies the full token count by the full input price. But 9,000 of those 10,000 input tokens were billed at a fraction of that price. So the formula over-reports, and it over-reports by the size of your cached prefix times the discount.

The Phase 3 module pricing.py makes the gap visible on one call. It prices the token split and also computes what the old formula would have said. The example prices input at $2.00, output at $8.00 and cached input at $0.50 per million tokens. That cached price is 0.25x input, not the 0.1x of the course price sheet, so the saving here is smaller than on a 0.1x model. At 0.1x the same call costs $0.0118.

c = cost(price, Usage(uncached_in=1_000, cached_in=9_000, out=1_000))

c.total         # 0.0145  -> the real invoice
c.naive_total   # 0.0280  -> what the Phase 1 formula says
c.overcharge    # 0.0135  -> money your old meter invented

Notice the size of the gap. The old formula reports $0.0280 against a real cost of $0.0145, so it invents 93% on this request. The warmer your cache, the larger the invented part, because the gap grows with the cached prefix.

You might think an estimate that runs high is safe. It is not, for two reasons. First, it hides savings you already earned, so you cannot prove caching work paid, and you cannot see the day it stops paying. Second, it inverts comparisons, because a routing decision between two models is a ratio. If one model caches well and the other does not, the overcharging meter prices the caching model as if it never hit, and it can pick the wrong model.

The module has one rule worth copying into any meter you write. A price sheet may not define a cached price for a model. The wrong instinct is to treat an unknown price as free, because that makes requests look cheaper than they are and prints no error. The module does the opposite. It falls back to the full input price, the most expensive thing the tokens could plausibly cost.

# unknown price becomes free
cached_rate = price.cached_input_per_mtok or 0.0

Every unpriced class makes the request look cheaper. The error grows silently as you add providers.

# unknown price becomes full price
cached_rate = (price.cached_input_per_mtok
               if price.cached_input_per_mtok is not None
               else price.input_per_mtok)

You over-report until you fill in the sheet, and over-reporting is the error you notice.

The failure this rule prevents is a dashboard that reports savings that do not exist. The self-test catches it. Check 8 expects $0.02 for 10,000 cached tokens at a $2.00 input price. With the zero fallback the total comes out $0.00, and the test prints [FAIL] unknown cached price falls back to full price.

Evidence
The three cost values above come from a run of python pricing.py --self-test checked on 2026-09-17, which printed 0.0145 0.028 0.0135. The zero-fallback failure was reproduced the same day by editing a copy of pricing.py to fall back to zero; it printed [FAIL] unknown cached price falls back to full price.

Use it. In the lab, E1 runs python pricing.py --self-test and then asks you to break the fallback yourself. A question to hold while you run it: which line of output would change if your price sheet lost its cached price tomorrow?

A bill has five token classes and two multipliers; a two-field meter cannot read it.

An overcharging meter feels safe, and it hides savings and inverts model comparisons.

Run python pricing.py --self-test and look for the line about unknown cached prices.

You now know the five classes exist. What you do not know yet is where each class lives inside the usage object, because OpenAI puts cached and write tokens inside input_tokens and Anthropic puts them outside it. The next section opens both objects and asks why the same field name means two different things.

## Why does the same field name mean two different things?

The same input_tokens number means different things per provider, so one shared summation is wrong.

The section above gave you the five token classes and a pricing.py that prices them. Those classes exist on both providers, but the number a class lives under differs, and that difference is where the meter goes wrong. Your Phase 1 meter sums usage.input_tokens and prices it, so this section asks what that number actually is on each provider.

The picture. Both providers send you the same five classes, but they pack them differently into the JSON. On OpenAI, the cached input count is inside input_tokens, so that field already includes tokens billed at the cheap rate. On Anthropic, the cached input and cache write counts sit outside input_tokens, which reports only the tokens after the last cache breakpoint. To get the uncached tokens that pay full price, you subtract on one provider and add on the other.

  OpenAI — subtract

  input_tokens = 12,400

  uncached
  400

  cached (read)
  12,000

  write
  0
  uncached = input_tokens − cached − write

  Anthropic — add

  input_
  tokens
  400

  cache_read_
  input_tokens
  12,000

  cache_
  creation
  0
  total input = input_tokens + cache_read
  + cache_creation
  input_tokens = tokens after the last breakpoint

The same 12,400-token warm request, as each provider reports it. Illustration built from the documented formulas, not measured.

The mechanism, step by step. Anthropic's documentation says the input_tokens field represents only the tokens after the last cache breakpoint in your request. So the identity on Anthropic is total_input = cache_read_input_tokens + cache_creation_input_tokens + input_tokens. A meter that prices input_tokens alone there misses the whole cached prefix.

OpenAI is the mirror. Its documented cost formula is ordinary input = input_tokens − cached_tokens − cache_write_tokens. A meter that prices input_tokens alone there re-bills the cached tokens at the full input rate. The same summation function is wrong in opposite directions on the two providers.

One more rule covers the nested detail counts, such as text_tokens and image_tokens. Those are subsets of the total, not additions to it. Adding them to the total double-counts every multimodal token they describe. So a multimodal meter can report up to twice the real bill that way.

The code shape this forces is a usage adapter, a small function per provider that turns that provider's usage object into one shared split of uncached_in, cached_in, write_in and out. cost_meter.py has both adapters in extract_usage at cost_meter.py:66, and it prints the shape it matched so a field-path mismatch shows up in the logs.

The one failure. A public issue against Langfuse documents what the wrong assumption costs on a dashboard. A fully instrumented multi-turn Claude run had a true cost of $0.52231845, and the dashboard computed $0.237606, about 46% of the real spend. The instrumentation sent no cache-read or cache-creation counts, and the dashboard displayed usage: {input: 20, output: 13545}. Twenty input tokens on a multi-turn agent run with a large system prompt was plainly wrong, but the wrong number rendered exactly like a correct one, and nothing errored.

Evidence
Reported in Langfuse issue #13807, read 2026-09-29. Conditions: @langfuse/otel 5.3.0, OpenInference Claude Agent SDK instrumentation 0.2.5, model claude-sonnet-4-6. The issue quotes the API response directly: "The API returned usage: {input: 20, output: 13545}. Twenty input tokens on a multi-turn run with a large system prompt."

Use it. Open the two adapters in extract_usage at cost_meter.py:66. Find the line where each one computes the total input. The question to answer: which of the two adapters would a copied Chat Completions code snippet need? And which one would it quietly replace?

OpenAI counts cached tokens inside input_tokens, Anthropic outside it, so subtract there and add here.

One shared summation looks correct on both providers and is wrong by the size of your cached prefix.

Read extract_usage in cost_meter.py and say which provider each branch is for.

Your meter can now read the bill correctly on both providers. What it still cannot explain is the second half of your invoice puzzle: the timestamp line from Phase 0 moved the bill without changing any token count. The next section asks what, besides a timestamp, breaks a cache hit.

## What else breaks a cache hit besides a timestamp?

Phase 2A gave you the layout rule; this section adds the parts of a request you do not think of as text.

Phase 2A measured the rule this section builds on. The cache matches the prefix, the start of your prompt from token 0 forward, and the match stops at the first byte that differs. So a timestamp at the top of the prompt gave a 0.0% hit rate in its simulator, and the stable-first layout gave 92.0%. Phase 0's Story 1 showed the same line moving an invoice from about $40 to over $200 on the same traffic.

Production numbers agree. ProjectDiscovery sends a system prompt of over 20,000 tokens on every step of an agent task, and it kept working memory near the top. Its cache hit rate, the share of input tokens billed at the cached read price, was 7.6%. Moving that memory into a tail message raised it to 73.7% in one deploy. Two of its tasks with nearly equal volume ran at 91.8% and 3.2%, and the post says the second cost roughly 60 times more. Hit rate alone does not explain that. With misses at the plain input price, the average price per input token at those rates differs about 5.6 times, and caching can never make it differ more than 12.5 times, a 1.25x write against a 0.1x read. The post does not show where the rest of the gap comes from. What 2A did not show is that the bytes include more than your text.

Predict: two back-to-back requests differ only in the order the tool definitions appear. Same model, same system prompt. Does the second request hit the cache?
No. Tool definitions are rendered into the request before the system and message text, so a different order means the bytes differ from the first tool onward. The match from token 0 stops at that byte, and the identical policy text below is billed at full price. The belief that this should hit is reasonable, because to you the two requests carry identical meaning. The cache never compares meaning, only the byte sequence.

Start from why the prediction holds. The server never sees your Go structs or your prompt builder, it sees one rendered request, and your settings are rendered into it. On OpenAI the matching covers the model, the tool definitions with their names, descriptions, schemas and ordering, parallel_tool_calls, the structured-output format in text.format, reasoning.effort, text.verbosity, and the context-management setting. Change any of these between two calls and the match breaks at that byte, even when every visible word of text is the same.

Anthropic publishes the same rule as an order of invalidation, tools, then system, then messages. A change at one level invalidates that level and every level below it. So editing one tool description costs you the whole system prompt as well, while editing the last user message costs only the tail after it. The same docs note that toggling web search, citations or the speed setting breaks the system and message levels, and adding an image anywhere breaks the message level.

The sharpest form of this bug lives in your own Go services. Go deliberately shuffles map iteration order, so any serializer that emits JSON keys by ranging over a map writes different bytes on different processes. Anthropic's docs warn about exactly this for tool_use blocks in history, and name Go and Swift. The symptom is a hit rate that changes from pod to pod with zero code changes, and the fix is to make the code that serializes your tool schemas emit a fixed key order through structs or explicit sorting.

```go
// Go shuffles map order: each pod writes the keys differently
for name, prop := range schema.Properties {
    fmt.Fprintf(&buf, "%q:%s,", name, prop)
}
```

Two pods send the same tool schema as different bytes, so the cache misses on one of them.

```go
// sort the keys: every pod writes the same bytes
for _, name := range slices.Sorted(maps.Keys(schema.Properties)) {
    fmt.Fprintf(&buf, "%q:%s,", name, schema.Properties[name])
}
```

Go's encoding/json already sorts map keys. The bug lives in hand-written loops like the first one.

So the layout rule from Phase 2A grows by two parts. Update the stable part append-only, adding new text below and never editing in place. And on Anthropic's explicit markers, put the breakpoint on the last block that stays identical across requests.

Evidence
The settings list is from the OpenAI prompt caching guide, opened 2026-09-29. The tools, system, messages invalidation order and the serializer warning are from the Anthropic prompt caching docs, opened 2026-09-29, which say verbatim: "Verify that the keys in your tool_use content blocks have stable ordering as some languages (for example, Swift, Go) randomize key order during JSON conversion, breaking caches." The hit rates and the two tasks are from ProjectDiscovery, "How We Cut LLM Costs by 59% With Prompt Caching" (the Neo platform, 20 to 40 steps per task, system prompts over 20,000 tokens), read 2026-09-29. The 0.0% and 92.0% are Phase 2A's simulator results.

Use it. The lab's E5 runs the timestamp experiment against the live API: the same prompt with the timestamp at position 0, then at the end. Watch one field, the cached count in the usage object. Then try the new part yourself: swap the order of two tool definitions between two calls and watch the same field.

Tool order, output format, reasoning settings and JSON key order are part of the bytes that must match.

A Go serializer that ranges over a map changes the bytes on every process, so the hit rate differs from pod to pod.

Diff the rendered request of two calls, not your prompt text, and find the first byte that differs.

Every number here rested on someone reading the cached-token count per request. That raises a question the layout rules cannot answer. What evidence does a hit leave behind, and what does a broken cache look like on the wire? The next section answers that: why a 200 OK proves nothing about caching.

## Why does success never prove caching?

ProjectDiscovery could act on their hit rate only because someone read it somewhere. This section asks what a cache hit actually leaves behind on the wire. The answer is one field, because the API reports a failed cache exactly the way it reports a working one.

Map this back to your support agent. You moved the timestamp line out of your prefix in the section above. Your code returned 200 OK before the move and after it. Your error monitor stayed quiet. Your token-count dashboard stayed flat. So how do you know the cache works now?

The picture first. A cache entry has a floor. The provider stores a prefix only if it is long enough. This floor is the minimum cacheable length, the smallest prefix the provider will store for a given model. Anthropic's minimums run from 512 tokens to 4,096 tokens depending on the model. OpenAI requires 1,024 tokens on GPT-5.6 and later. When your prefix sits below the floor, the provider processes the request at full price and returns success. When your prefix sits above the floor but does not match, the same thing happens. Both failures look identical to a hit everywhere except one field in the usage object.

Predict: You marked an 800-token prefix with cache_control, the marker that asks Anthropic to store the prefix ending at that block, and got 200 OK on both calls. Were you cached? What single field proves it?
It depends on the model's floor, and you cannot tell from the status code. Anthropic's minimums start at 512 tokens on current models such as Opus 5.5 and Sonnet 5.5, and reach 4,096 on others such as Haiku 4.5. So 800 tokens is above the floor on some models and below it on others. Below the floor, the provider processed the prompt at full price and returned success with no error. The only proof one way or the other is usage.cache_read_input_tokens on the second call. A large number there proves a hit, and zero proves nothing was read. The HTTP status carries no information about caching in either direction.

The mechanism has three steps, and each one explains why your error monitor is the wrong tool.

- The provider decides the floor from the model alone. A prefix of 800 tokens on a model with a 4,096-token minimum is processed without caching, and the provider treats this as normal operation, not a failure. Anthropic's documentation states that any request to cache fewer tokens than the minimum is processed without caching and returns no error. On OpenAI the same rule holds at 1,024 tokens, and on models before GPT-5.6 the minimum also varies with your settings, so a settings change can move the floor under an unchanged prompt.

- The response is identical in every field except the cache counts. The status is 200, the finish_reason is the same, and the token count on the wire is the same, because your prefix traverses the API either way. What changes is only the billing class of those tokens: full price on a miss, 0.1x on a hit, and 1.25x on a write. That is why a token-count dashboard shows a flat line while the bill doubles.

- The cached-token count is where the truth lands. Your usage adapter, the per-provider function from the earlier section that unpacks the usage object, already reads this count to price the call. That count is the proof of a hit. A count that reads large for weeks and then reads zero, while token counts stay the same, is the failure signal. No other signal exists.

The figure shows the same response twice, once after a hit and once after a silent miss. Every field matches except the two cache counts. Both add up to the same total input: 350 + 12,400 = 12,750 tokens.

{
  "status": 200,
  "usage": {
    "input_tokens": 350,
    "cache_creation_input_tokens": 12400,
    "cache_read_input_tokens": 0,
    "output_tokens": 412
  }
}

{
  "status": 200,
  "usage": {
    "input_tokens": 350,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 12400,
    "output_tokens": 412
  }
}

Both responses are success. The one on the left found no match, so it wrote the whole 12,400-token prefix again at 1.25x the input price. The one on the right read it at 0.1x. You can only tell them apart by reading the two cache fields.

Evidence
Anthropic's prompt caching documentation, read 2026-09-29: "Any requests to cache fewer than this number of tokens will be processed without caching, and no error is returned. To verify whether a prompt was cached, check the response usage fields." The same page lists the minimums, from 512 tokens on Fable 5.1, Mythos 5.1, Opus 5.5 and Sonnet 5.5 up to 4,096 tokens on Opus 4.6, Opus 4.5 and Haiku 4.5. The OpenAI prompt caching guide, read the same day, sets the minimum at 1,024 tokens on GPT-5.6 and later and notes that on earlier models it varies with tools, images, schemas, reasoning effort and verbosity.

Try this now: run python phase03_economics/cost_meter.py --model <your-model> --role cache_demo --prefix-tokens 400 in live mode, which is exercise E6. Both calls return 200 OK, and the cached count reads zero on both. Then read the diagnosis the script prints, which is the check this section just taught.

A broken cache returns 200 OK, and the cached-token count in the usage object is the only proof.

"If caching broke we would see errors" costs you the full-price premium on every request. Your error monitor sees nothing.

Run E6 with --prefix-tokens 400 and confirm the cached count reads zero on a 200 response.

This is also the observation the alarm in Phase 3B is built on. An error monitor will not catch a cache that stopped, because there is no error. So the alarm watches the cached count per request and fires when it stays at zero.

You can now prove a hit happened. You still cannot say whether that hit was worth buying, because the write costs more than the input it replaces. The next section answers that: when does a cache entry pay for itself?

## When does a cache entry pay for itself?

Knowing a hit exists is not enough to know it was worth buying. The write costs more than the input it replaces.

A cache entry is a purchase, and the purchase only pays if you read it enough times.

Your support agent reads the same policy text on every turn. The section above gave you the cached count that proves the hit. This section gives you the arithmetic that decides whether the hit was profit.

The price sheet has three rates for the same 12,000 tokens of policy text. Plain input costs 1.0x. A cache write costs more than plain input, because the server stores the KV state for you. A cached input, which is a read from the stored entry, costs 0.1x. So the discount from the last section is real, but the first turn pays a surcharge to create it.

- turn 1: write12,000 tokens at 1.25x, plus the reply

- turn 2: read12,000 tokens at 0.1x, before the entry expires

- turn 3: readanother 0.1x, if the entry is still alive

The lifetime you buy is the TTL, the time to live of a cache entry. Anthropic sells two tiers: 5 minutes at a 1.25x write rate, and 1 hour at 2x. After the TTL passes, the entry is gone and the next request writes again.

Predict: a 5-minute write costs 1.25x and a read costs 0.1x. Your agent writes an entry and reads it once before it expires. Did caching save money or lose it on that entry, and by how much?
It saved money. Buying the entry cost an extra 0.25x over plain input for that write. The read saved 1.00x minus 0.10x, which is 0.90x. Net result across the two requests: a saving of 0.65x the input tokens.

Compare it with the uncached path. Without caching, two requests cost 2.00x. With caching, the write plus one read costs 1.25x plus 0.10x, which is 1.35x.

The derivation is arithmetic on three rates. Write the extra cost of creating the entry as write rate minus input rate. Write the saving per read as input rate minus read rate. The break-even in reads is the first number divided by the second.

reads needed = (write rate − input rate) / (input rate − read rate)

5-minute tier: (1.25 − 1.00) / (1.00 − 0.10) = 0.25 / 0.90 = 0.28
1-hour tier:   (2.00 − 1.00) / (1.00 − 0.10) = 1.00 / 0.90 = 1.11

At the 5-minute tier, 0.28 reads rounds up to one read, so the first hit already turns a profit. At the 1-hour tier, 1.11 reads means two reads before you break even. The multipliers will change over time, and the formula does not. Recompute from your own price sheet rather than remembering 0.28.

  Break-even in reads, from multipliers

  Write rate (x input)

  Read rate (x input)

  Reads needed

  In practice, reads before profit

The break-even tells you which tier fits a workload by looking at read spacing. A fast tool-calling loop reads every few seconds. The 5-minute entry stays alive, and one read already paid for it. A human conversation with ten-minute pauses kills the entry between turns, so each turn pays the write again at 1.25x.

That last case is a workload that reads once or not at all per write. The 1-hour tier keeps the entry alive across those pauses, but one read is not enough. A write plus one read pays 2.00x plus 0.10x, which is 2.10x. Two plain calls cost 2.00x, so with one read the 1-hour tier still loses to no caching. It only beats the 5-minute tier, where both calls pay a 1.25x write, which is 2.50x. A write plus two reads pays 2.00x plus 0.20x, which is 2.20x, against 3.00x for three plain calls. The second read is where the 1-hour tier moves into profit.

One detail changes the tier decision for slow responses. Anthropic measures the TTL from the start of the request, not from the end of its response. A 5-minute entry written by a request streams for 4 minutes. It has 1 minute of life left when the reply finishes. So a long streaming workload can outlive its own cache before a follow-up request arrives.

Evidence
The multipliers and the TTL-from-request-start rule come from the Anthropic prompt caching docs, read 2026-09-29. They are 5-minute write at 1.25x, 1-hour write at 2x, reads at 0.1x with model exceptions. The OpenAI prompt caching guide was read the same day. It shows the same 1.25x write and 0.1x read on GPT-5.6 and later. The break-even numbers are arithmetic on those rates, not a measured run.

A cache write is a surcharge, and the entry pays for itself after (write − 1) / (1 − read) reads.

"Caching is free to turn on" costs 1.25x input on every entry that expires before its first read.

Compute the break-even from your prices.yaml once; compare the answer with the reads-per-write your agent actually makes.

The break-even assumed the entry gets read at all. One common call pattern writes entries and reads none of them. The next section asks why ten parallel calls cost more with caching on.

## Why do ten parallel calls cost more with caching on?

The break-even from the last section assumed each entry gets read. There is one call pattern where the entries are written and not one is read, and it is a pattern a support agent hits on its first deploy.

Say you ship a new system prompt on Monday at 9:00 and your traffic spike starts ten agent calls in the same second. All ten share the same 12,000-token prefix, and caching is on. Your natural expectation, after the break-even section, is that call 1 writes and calls 2 to 10 read. That is not what happens.

The reason is one rule about availability. A cache entry is usable only after the first response to it begins. Both providers document this. Ten calls that start together all arrive before any response begins, so all ten find an empty cache. Each pays the cache write premium, 1.25x the input price, and not one of them gets the 0.1x read price. This pattern has a name: a cold-start fan-out is a group of same-prefix calls started together against an empty cache. Each member writes an entry and each member reads nothing.

  All ten at once: 10 writes, 0 reads

    calls 1–10 start before any response begins
    each pays 1.25x, nothing reads

  Warm-up first: 1 write, 9 reads

    call 1 writes; its response begins

    calls 2–10 start after it, at 0.1x

-

-
  entry becomes usable

Order of events for the two sequences. Shape from the provider rule, not measured timings.

Now put the course price sheet on it. The sheet prices input at $2.00 per million tokens, a cache write at 1.25x so $2.50, and a cache read at 0.1x so $0.20. All ten calls below use the same 12,000 tokens of input, so only the billing class differs.

Ten calls at once. Step 1: calls 1 to 10 start, no entry exists yet. Step 2: ten writes, zero reads. The cost is 10 × 12,000 × $2.50 / 1e6.

Total: $0.300

One warm-up, then nine. Step 1: call 1 starts, no entry exists. Step 2: call 1's response begins, so the entry becomes usable. Step 3: calls 2 to 10 start, and they read. The cost is 12,000 × $2.50 / 1e6 plus 9 × 12,000 × $0.20 / 1e6.

Total: $0.0516

Same ten calls, same tokens: the wrong order costs $0.300 and the right order costs $0.0516.

Two numbers in that chart deserve a second look. The middle bar is the trap's price: running the fan-out with caching on costs 25% more than running it with caching off, because every one of the ten writes was paid for and none was used. The outer bars give the section's headline: ordering alone moves the same traffic by 5.8x ($0.300 against $0.0516), and the code change is to let the first call finish its first tokens before the other nine start.

Evidence
The availability rule is quoted in the provider docs, read 2026-09-29: "a cache entry only becomes available after the first response begins. If you need cache hits for parallel requests, wait for the first response before sending subsequent requests." The dollar figures are arithmetic on the course price sheet (gpt-5.6-terra row: input $2.00, write $2.50, read $0.20 per MTok), not a measured run.

This failure has the same shape as a mistake you already know. In Phase 2B you saw that front-truncating the conversation history keeps the token count fine and still changes the prefix of every later request, so none of them match. One version breaks the prefix by editing bytes; this one breaks it by starting every request too early. In both cases the tokens on the wire look unchanged and only the billing class moves.

The fix follows the availability rule directly: sequence the burst. Send one warm-up call with the new prefix, wait for its first tokens, and then start the parallel calls. Your orchestration loop already knows how to wait, so this is a scheduling change, not a caching change.

An entry is usable only after its first response begins, so ten simultaneous same-prefix calls write ten entries and read zero.

Turning caching on for a cold-start fan-out costs 25% over plain input price, because ten writes at 1.25x are paid and none is read.

Add one 5-second stagger to the next batch of identical agent calls and compare the cached counts before and after.

That closes the teaching part of the phase. You can now read any usage object into a correct cost, lay out a prompt that caches, and prove both with numbers from your own account. The recall section gathers the four claims, and the next phase asks the harder question: how do you notice within ten requests, instead of four months, that the cached count dropped to zero while every request still returned 200.

## What you can do now, and what comes next

You started this phase with a meter that matched no invoice. Seven sections later you can explain both directions of the error. Read the four claims again; they should now read as things you would say yourself.

One field name, two meanings

On OpenAI the cached and written tokens sit inside input_tokens. On Anthropic they sit outside it in two extra fields. So one shared summation is wrong by the size of your cached prefix, in either direction. The fix is one usage adapter per provider. The Langfuse dashboard that showed 20 input tokens and $0.238 for a $0.522 run is what skipping the adapter costs.

Hit rate is your layout

The cache matches bytes from token 0 forward. Those bytes include tool order, output format, and your Go serializer's key order, not only your text. Keep stable content first and volatile content in a tail block. ProjectDiscovery moved the volatile part out and went from 7.6% to 73.7% hits in one deploy.

Success proves nothing

Below the model's minimum cacheable length, the provider caches nothing and returns no error. The token count on the wire is identical either way. Only the billing class changes. The cached-token count in the usage object is the single proof a hit happened, and a count that falls to zero is the only failure signal.

Caching is a purchase

A write costs 1.25x or 2x the input price and a read costs 0.1x. An entry pays for itself after (write − input) ÷ (input − read) reads. An entry becomes usable only after the first response begins. So ten parallel same-prefix calls write ten entries and read zero, and cost more than no cache at all.

Each claim has a home in the phase. The first belongs to the sections that opened the usage object on both providers. The second belongs to the section on what breaks a cache hit, with the ProjectDiscovery numbers. The third belongs to the section on silent failure. The fourth belongs to the two sections on break-even arithmetic and the cold-start fan-out.

What you can do now is concrete. You can read any usage object into a correct cost. You can lay out a prompt so the cache hits. You can prove both from numbers in your own account, and the lab walks you through exactly that.

One gap remains, and it is the thread the whole phase has been pulling on. Every failure here is silent. Nothing errors. The next phase asks the hard question: how do you notice within ten requests, instead of four months, that your cached count fell to zero while every request returned 200.

## Lab: the money arithmetic, the hit, and the break-even

Each exercise below proves a claim from the section named under it. The offline ones cost nothing and run tonight. The live ones are marked UNVERIFIED, because no API key was available when the phase was written, so their flags were checked against each script's --help rather than run against a provider.

Setup: cd ~/Desktop/project/code/study-material/inference-internals/code && uv sync. The author first ran every offline command on 2026-09-12, and a review re-ran them on 2026-09-17, so the Expected lines below match that run.

-
 E1 offline
Proves the first claim: the meter is software with a correctness property, and an unknown price falls back to full price, never zero.

Run: python pricing.py --self-test

Expected: 13 checks pass, and the last line is all checks passed. One check is "unknown cached price falls back to full price". A WARNING line about tier mystery also appears. That warning is expected, because one check uses an unknown tier on purpose.

Then break it on purpose. Open pricing.py at line 164. Change the fallback to 0.0, and run the test again. That check now fails and names the mistake you made. Change it back.

-
 E2 offline
Proves two claims at once: the price sheet drives every number in the phase, and a missing cached price hides the saving silently.

Run: python pricing.py --role deep then python pricing.py --role cheap

Expected: a Price(...) row for each. Each row ends with cached_input_per_mtok=None. The next line is cached price NOT SET for this model. A row with a cached price prints cached/input ratio: ... instead. Try python pricing.py --role cache_demo to see 0.100.

Then edit prices.yaml. Replace both models with the ones you use. Fill in every field you can find on the provider's pricing page. Set priced_on to today. If you cannot find a field, leave it out. Do not guess it, because a guessed price produces a wrong answer that looks certain.

-
 E3 offline
Proves the first claim with numbers: the old formula overstates the warm call by 76.1%, and the size of the saving is visible before you spend anything live.

Run: python phase03_economics/cost_meter.py --replay --role cache_demo

Expected: the cold call shows a gap of $0.000000. The warm call shows the naive formula overstating by 76.1%. The warm call is 4.18x cheaper than the cold call. The batch lines show $0.003400 for the warm batched call, 8.35x cheaper than the cold call.

Then run it with --role deep and with --role cheap. Both show a gap of zero and 1.00x cheaper, then a WARNING line. Neither row has a cached price, so the ratio is 1.00 by construction. The batch lines still halve the cost, for example $0.027200 to $0.013600 for deep. A missing price hides the saving completely.

-
 E4 live, unverified
Proves the silent-failure claim: the cached-token count is the only proof that caching works.

Run: python phase03_economics/cost_meter.py --model <your-model> --role cache_demo

Expected: call 1 reports 0 cached tokens. Call 2 reports most of the 12,000-token prefix as cached. The gap column shows the naive formula overstating by more than half.

If call 2 also reports 0: read the diagnosis the script prints. The usual causes are a prefix below the minimum, or too long a pause between calls. A gateway that drops the details object is a third cause.

Costs at most: about $0.05.

-
 E5 live, break-it, unverified
Proves the layout claim in the strongest way this phase has: about 25 characters at position 0 cost the whole discount.

Edit build_prompt at cost_meter.py:56. Put the current timestamp at the start of the returned prompt, at position 0. Run E4 again.

Expected: call 2 now reports 0 cached tokens, and the true cost equals the naive cost.

Then move the timestamp to the END of the prompt and run it again. The hit comes back. This is Phase 0's Story 1 on your own bill, in two minutes. Remove your edit afterwards.

-
 E6 live, break-it, unverified
Proves that below the minimum, success proves nothing: both calls return 200 and both report 0 cached, with no error anywhere.

Run: python phase03_economics/cost_meter.py --model <your-model> --role cache_demo --prefix-tokens 400

Expected: both calls succeed, and both report 0 cached tokens. Nothing in the output says why. A prefix below the documented minimum does nothing and raises no error.

Then raise it to 1,200 and watch the hit appear. The lack of an error does not prove that a feature works.

-
 E7 live, unverified
Proves the purchase claim: explicit caching is a purchase with a payback period, and turn 1 of the cached run costs MORE than the control.

Run offline first: python phase03_economics/cache_control_lab.py --explain. Read the block order and the usage fields it names.

Then: python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5. Run it again with --no-cache.

Expected: the script prints the break-even in reads before the first turn. Turn 1 of the cached run costs MORE than the control, because you paid the write premium. By turn 2 or 3, the cached run's running total drops below the control's. Write down which turn.

Costs at most: about $0.10 for both runs.

-
 E8 live, break-it, unverified
Proves the purchase and layout claims together: a volatile block above the breakpoint makes you pay 1.25x on every turn and read nothing back.

Run: python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5 --break-it

Expected: every turn shows a non-zero written column and a zero read column. You paid 1.25x input on every turn. This run costs more than a run with caching turned off.

Compare this total with the --no-cache control from E7, and write down the difference. This is the same failure as E5, seen from the billing side: one volatile block above the breakpoint reverses the benefit of the whole feature.

The checkpoint comes next. It asks you to do the same arithmetic without the scripts: what would you expect to see, and what would you conclude.

## Checkpoint 3A

Write your own answer to each question before you open the sketch. The numbers here are small enough to do on paper, and the point is the reasoning, not the arithmetic.

-
Show the math. A model has these prices per million tokens: input $2.00, cached input $0.20, cache writes $2.50, output $12.00. Your agent step sends 20,000 input tokens. Of those, 18,000 hit the cache. The step generates 400 output tokens. (a) Compute the true cost. (b) Compute what the Phase 1 two-price formula would report. (c) State how many times higher the old meter's number is. (d) Your finance team uses the old number to set customer prices. Name the business error that this creates.

Answer sketch
(a) Uncached input is 20,000 − 18,000 = 2,000 tokens. 2,000 × $2.00 / 1e6 = $0.004. Cached input is 18,000 × $0.20 / 1e6 = $0.0036. Output is 400 × $12.00 / 1e6 = $0.0048. The true total is $0.0124.

(b) Naive: 20,000 × $2.00 / 1e6 + $0.0048 = $0.04 + $0.0048 = $0.0448.

(c) $0.0448 / $0.0124 = about 3.6x.

(d) You set prices against a cost 3.6x higher than your real cost. You lose deals you could have won. You also cannot explain your own margin when someone checks the invoice.

-
Three causes. A colleague says: "We turned on prompt caching and our costs did not move. So caching does not work for our workload." Give three separate, specific causes of that observation. For each cause, name the one number you would check to confirm or rule it out.

Answer sketch
Here are three causes, each with the number that confirms it.

- The prefix is below the minimum. Nothing caches, and no error appears. Check the cached-token count. It is exactly 0 on every call.

- Something volatile sits early in the prompt, so every request is cold. The cached count is also 0. To tell this apart from the first cause, make the prefix longer and see whether anything changes.

- The saving is real, but your meter cannot see it. Check whether your code reads the cached-token field at all. If it does not, your cost number can never move.

A fourth answer is also correct. Writes cost 1.25x. A workload with many writes and few reads does not save money.

-
Show the math, then decide. A provider charges 2x input for a one-hour cache write, 1.25x for a five-minute write, and 0.1x for a read. (a) Derive the number of reads needed before the one-hour tier makes a profit. (b) Your agent makes one call every 12 minutes for an hour. Which tier do you pick, and why? (c) Your agent makes one call every 20 seconds for two minutes, then stops. Which tier do you pick, and why is the answer different?

Answer sketch
(a) (2.00 − 1.00) / (1.00 − 0.10) = 1.11, so two reads.

(b) With a 12-minute gap, a five-minute entry always expires before the next call. That tier gives you a write every time and no reads. The one-hour tier gives one write and four reads within the hour. Four reads clear the two-read break-even. Pick one hour.

(c) Calls 20 seconds apart never let a five-minute entry expire. So the cheaper 1.25x write is already reused. The extra 0.75x for the longer tier buys nothing. Pick five minutes.

-
This is broken. Your cost dashboard reports $0.24 for an agent run. The provider billed $0.52. The dashboard shows 20 input tokens and 13,545 output tokens. The run had many turns and a large system prompt. (a) Name the cause. (b) Explain why 20 input tokens should have looked wrong to any reader. (c) Name the two missing usage fields. (d) Say why this kind of bug gets through code review.

Answer sketch
(a) The instrumentation did not send cache-read or cache-write tokens. So the tool recomputed the cost from partial counts.

(b) On that provider, input_tokens counts only the tokens after the last cache breakpoint. A multi-turn run with a large system prompt cannot have only 20 real input tokens. The tool read the field as if it meant total input.

(c) cache_read_input_tokens and cache_creation_input_tokens.

(d) The wrong number looks plausible. It comes through the same code path as correct numbers. Nothing raises an error. Only a comparison with the provider's own cost report catches it.

-
Walk me through what happens. Your agent gets a burst of 10 identical requests at once, at cold start. Each carries the same 12,000-token system prompt. The provider charges 1.25x for cache writes. (a) Trace what the cache does across those 10 requests. (b) Compare the total input cost with the same 10 requests with caching turned off. (c) State the one change to your call pattern that fixes it, and its latency cost.

Answer sketch
(a) A cache entry becomes usable only after the first response begins. All 10 requests start before any entry exists. So all 10 write, and none read.

(b) With writes at 1.25x, the 10 requests cost 1.25 times the cost with caching turned off. For the 12,000-token prompt at $2.00 input, that is $0.300 against $0.240. Caching made this burst more expensive.

(c) Send one warm-up call. Wait until its response starts. Then send the other 9 against the warm entry. The cost is the latency of one extra round trip at the start of the burst.

The cheatsheet comes next. It collects the five token classes, the field paths, the break-even formula and the lab commands on one page for when you need them again.

## Cheatsheet

THE FIVE TOKEN CLASSES, AND TWO MULTIPLIERS
  classes:     uncached input | cached input (READ) | cache WRITE | output
  multipliers: service tier (batch/flex/priority/region) | modality (image/audio)
  Phase 1 had two classes and no multipliers.
  unknown price → fall back to FULL input price, never to 0.0
  unknown tier  → price at STANDARD and warn, never invent a discount
  nested detail counts are SUBSETS of the total. Adding them double-counts.
  one provider EXCLUDES its priority tier from the cost endpoint entirely

THE USAGE FIELD PATHS
  OpenAI Chat        usage.prompt_tokens_details.cached_tokens / .cache_write_tokens
  OpenAI Responses   usage.input_tokens_details.cached_tokens  / .cache_write_tokens
  Anthropic          usage.cache_read_input_tokens
                     usage.cache_creation_input_tokens
                     usage.cache_creation.ephemeral_5m_input_tokens / _1h_
  OpenAI    cached tokens are INSIDE prompt_tokens  → subtract
  Anthropic cached tokens are OUTSIDE input_tokens  → add
  total_input = cache_read + cache_creation + input_tokens   (Anthropic)
  ONE ADAPTER PER PROVIDER. Never share the summation code.

IMPLICIT CACHING (automatic)
  minimum prefix 1,024 tokens (OpenAI, GPT-5.6+) | 512-4,096 by model (Anthropic)
  read 0.1x input | WRITE 1.25x input  ← caching is no longer free to try
  lifetime 30 min sliding (current OpenAI) | 5 min from last use (Anthropic)
  below the minimum: caches nothing, returns NO error
  cold-start fan-out of N parallel calls = N writes, 0 reads

EXPLICIT CACHING (cache_control)
  at most 4 breakpoints | 20-block backward lookback
  order is fixed: tools → system → messages
  break-even reads = (write_rate - input_rate) / (input_rate - cached_rate)
    1.25x write → 0.28 reads → profits on read 1
    2.00x write → 1.11 reads → profits on read 2
  1h tier wins when gaps between calls exceed 5 minutes
  TTL runs from the START of the request, not the end of its response
  volatile block ABOVE the breakpoint = a write every turn, forever

WHAT BREAKS A HIT
  any byte change before the boundary | tool definitions AND their ORDERING
  parallel_tool_calls | structured-output format | reasoning effort | verbosity
  adding or removing an image | non-deterministic JSON key order (Go, Swift)
  front-truncating history | a different org, workspace, or region

PROOF AND FAILURE
  cached-token count in usage is the only proof caching happened
  count drops to zero with 200s and unchanged tokens = the cache is broken
  an error monitor never sees it

THE COMMANDS (part A)
  pricing.py --self-test                     → the money arithmetic, 13 checks
  pricing.py --role deep                     → read your own price sheet
  cost_meter.py --replay --role cache_demo   → the size of the saving, offline
  cost_meter.py --model X --role cache_demo  → a real cache hit, live
  cache_control_lab.py --explain             → the request shape, offline
  cache_control_lab.py --model X --role claude          → explicit caching
  cache_control_lab.py --model X --role claude --break-it → pay forever

  Part B covers routing cascades, batch APIs, and per-request cost alerting.

## What you could post

The input_tokens field means two different things on OpenAI and Anthropic, so one shared summation priced a $0.522 run at $0.238 with no error anywhere. The fix is one adapter per provider, because the wrong number renders exactly like a correct one.

Ten parallel calls with the same 12k-token prefix cost $0.300 with caching on, $0.240 with caching off, because a cache entry exists only after the first response begins. One warm-up call then nine reads costs $0.0516, so ordering swings the same traffic by 5.8x.

## Sources

Every link below was opened and checked on 2026-09-29. Prices and minimums in this area change faster than anything else in the course, so treat every number the phase quoted from them as a dated value and read your own price sheet for today's figures.

- Anthropic prompt caching — gave the explicit caching mechanics: breakpoints and the 20-block lookback, the 512 to 4,096 token minimums by model, the write multipliers (1.25x five-minute, 2x one-hour) and 0.1x reads, the invalidation order (tools, system, messages), TTL measured from request start, the automatic mode, and the rule that a cache entry is usable only after the first response begins.

- OpenAI prompt caching guide — gave the usage cost formula (input_tokens includes cached and write tokens, so ordinary input subtracts them), the 1,024-token minimum, the settings that invalidate a match (tool order, response format, reasoning effort, verbosity), and the new explicit options including a 30-minute TTL and prewarm.

- Anthropic rate limits — gave one fact: on most models only uncached input tokens count toward the input tokens-per-minute limit, so a high hit rate buys rate-limit headroom as well as money.

- Langfuse issue #13807 — gave the production proof that the field-name difference is not academic: a fully instrumented run with true cost $0.52231845 displayed as $0.237606, with usage.input: 20 on a multi-turn agent with a large system prompt, and no error anywhere.

- ProjectDiscovery, "How We Cut LLM Costs by 59% With Prompt Caching" — gave the layout evidence: an autonomous security-testing platform with system prompts over 20,000 tokens moved dynamic content out of the prefix and raised its weekly hit rate from 7.6% to 73.7% in one deploy, and two equal-volume tasks at 91.8% and 3.2% hit rates differed in cost by roughly 60x by the post's own account, more than the hit rates alone can explain.

- Google context caching and Google legacy caching page — gave the third provider's shape: implicit caching on by default for Gemini 2.5 and later but with no cost-saving guarantee, and explicit caching billed on cached tokens plus storage duration.

One sincere gap: the Deriv production write-up (85.8% hit rate, 77% input-cost cut) was not opened this run, so those numbers are not cited anywhere above. A widely shared "$47,000 runaway bill" story traces only to secondary posts with no first-party source; skip it too.
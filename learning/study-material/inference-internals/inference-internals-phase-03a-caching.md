# Phase 3A — The bill and the cache (the phase that pays for the course)

Phase 1 taught you to measure one request. Phase 2 taught you what the server does with it. This phase is about the bill. It starts with a problem in the meter you built in Phase 1.

That meter is wrong. It prices every input token at the full input price. Real providers bill input tokens in several classes. The cheapest class costs a tenth of the most expensive one. A meter that cannot see the classes reports a number that is too high. That error is not safe. It hides the savings you already get, and it hides the moment you stop getting them.

Phase 1's codebase-anchor question asked you to find that gap. Phase 0's Story 1 showed what happens when nobody finds it. A timestamp sat near the top of a team's prompt, so their cache never matched. They paid full price on every agent step for four months.

Phase 3 has two documents, because it covers five separate topics. This is part A.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PART A, this document                                                    │
│  3.1  The five token classes   — why the Phase 1 formula overcharges     │
│  3.2  Implicit prefix caching  — automatic, invisible, and easy to lose  │
│  3.3  Explicit caching with    — you place the boundary and pay to write │
│       cache_control              it, so it needs a break-even            │
│                                                                          │
│ PART B, the next document                                                │
│  3.4  Routing cascades and     — quality per dollar, and the control     │
│       batch APIs                 group that most write-ups skip          │
│  3.5  Per-request cost         — the detector Story 1 needed             │
│       alerting                                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

After part A you can do four things:

1. Read a provider's real invoice from the `usage` object.
2. Lay out a prompt so the cache hits.
3. Prove the hit rate with a number.
4. Decide whether explicit caching pays for itself, from your own break-even arithmetic.

Time: 1.5 to 2 hours. All three scripts in part A have an offline mode with no API key. E4 to E8 need a key.

Setup:

```bash
cd ~/Desktop/project/code/study-material/inference-internals/code
uv sync                   # or: pip install -e .   Phase 3 adds the anthropic package
python pricing.py --self-test
```

The last command must print "all checks passed" before you start. Everything in this phase computes money, so you test the arithmetic first.

---

## 3.1 — The five token classes, and two multipliers (why your meter overcharges)
Why this matters: you cannot tune a bill you cannot read. Two numbers are not enough to read this bill.

Phase 1's formula was:

```
cost = input_tokens x input_price + output_tokens x output_price
```

A real request can contain these classes instead:

```
┌──────────────────┬────────────────────────────────┬───────────────────────┐
│ class            │ what it is                     │ typical price         │
├──────────────────┼────────────────────────────────┼───────────────────────┤
│ uncached input   │ prompt tokens the server had   │ the headline input    │
│                  │ to process this time           │ price                 │
│ cached input     │ prompt tokens served from a    │ a fraction of the     │
│ (a READ)         │ stored prefix                  │ input price           │
│ cache write      │ tokens stored into a cache     │ a PREMIUM above the   │
│                  │ entry, on providers that       │ input price, on       │
│                  │ charge for it                  │ explicit caching      │
│ output           │ generated tokens               │ several times input   │
│ batch            │ not a class: a multiplier      │ a flat discount on    │
│                  │ applied to the whole request   │ the whole request     │
└──────────────────┴────────────────────────────────┴───────────────────────┘
```

A prefix is the start of the prompt, from token 0 up to some position. Three of those five rows did not exist in your Phase 1 meter. So that formula reports a number larger than your invoice.

### Two more axes that are not token classes at all

The table above splits tokens by how the server processed them. Two other things change the same invoice without changing any token count. A meter that ignores them can be wrong in both directions.

**The service tier multiplies the whole request.** A service tier is a speed and price level per request. Batch is the tier you already met, at half price. Providers also sell tiers in the other direction. One is a slower tier priced below standard. Another is a faster, higher-priority tier priced above standard. The tier applies to every class at once. So it is a multiplier, not a price.

This has two practical results:

1. On at least one provider, the tier appears in the usage object as a `service_tier` field. So you can record the tier you were charged for, not only the tier you asked for.
2. This one catches finance teams. On one provider, the priority tier uses a different billing model. It **is excluded from the cost-reporting endpoint entirely**. You must read the usage endpoint instead. A reconciliation job that queries only the cost endpoint will under-count, and it will not tell you.

There is a third multiplier in the same family. At least one provider charges 1.1x for pinning inference to a specific region. That multiplier applies to cached reads and writes as well as to fresh input.

**Modality changes the price of an input token.** Modality means the kind of input, such as text, image, or audio. The provider converts image and audio inputs to tokens. Those tokens often cost more than text tokens. The provider reports them separately. They appear in nested fields such as `image_tokens` and `audio_tokens`. These fields sit in the same details object that carries the cached count.

The OpenTelemetry conventions state the same rule for their attributes:

```
  the detailed counts are SUBSETS of the total, never additions to it

  usage.prompt_tokens                    300   ← the total you are billed on
    prompt_tokens_details.text_tokens    100   ┐
    prompt_tokens_details.image_tokens   200   ├ these SUM to the total
    prompt_tokens_details.cached_tokens   40   ┘ and cached overlaps them

  WRONG:  total = prompt_tokens + image_tokens        (double counts)
  RIGHT:  total = prompt_tokens
          image_tokens tells you WHICH of them cost more

  the numbers above are an example
```

A multimodal cost meter that adds the nested counts to the total can report up to double the real bill. `pricing.py` models the surcharge, not a separate price. It charges an image token the text rate once. Then it adds only the extra on top. Its self-test proves that arithmetic:

```
  [ok ] image surcharge adds only the EXTRA
  [ok ] no surcharge when the model has no image price
  [ok ] flex tier halves the whole request
  [ok ] unknown tier prices at the standard rate
```

The last check follows a rule from this section. An unknown tier prices at the **standard** rate and prints a warning. It never guesses a discount. A guessed discount is an error you do not notice.

**Why an overcharge is still a bug.** An estimate that is too high feels safe. It is not safe, for two reasons.

1. It hides your own wins. Say caching already cuts your bill by half and your meter cannot see it. Then you cannot prove the work was worth doing. You also cannot tell when it stops working.
2. It breaks every comparison you build on top. A routing decision between two models is a ratio. Say one model caches and the other does not. An overcharging meter then compares them on the wrong basis. It can pick the wrong model.

**The fix, as code.** Phase 3 ships `pricing.py`. It is one module, and every later script imports it. It has one job: turn a token split into money.

```python
from pricing import Price, Usage, cost

price = Price(name="example", provider="x", model="x",
              input_per_mtok=2.00, output_per_mtok=8.00,
              cached_input_per_mtok=0.50)     # a quarter of the input price

# A warm agent step: 9,000 tokens hit the cache, 1,000 did not.
c = cost(price, Usage(uncached_in=1_000, cached_in=9_000, out=1_000))

c.total         # 0.0145  -> the real invoice
c.naive_total   # 0.0280  -> what the Phase 1 formula says
c.overcharge    # 0.0135  -> money your old meter invented
```

These are the same prices and counts as check 2 in `pricing.py:215` to `pricing.py:220`. A run on 2026-09-17 printed `0.0145 0.028 0.0135` for the three values. Verify it on your machine:

```bash
python pricing.py --self-test
```

One design decision in that module is worth copying into your own code. The price sheet may not define a cached price. Then the module falls back to the **full** input price, not to zero. The RIGHT version below is the shipped code at `pricing.py:164`.

```python
# WRONG: an unknown price defaults to free. Every unpriced class now makes the
# request look cheaper than it is, and the error grows silently as you add
# providers whose sheets you have not filled in.
cached_rate = price.cached_input_per_mtok or 0.0

# RIGHT: an unknown price defaults to the most expensive thing it could be.
# You will over-report until you fill in the sheet, and over-reporting is the
# error you notice.
cached_rate = (price.cached_input_per_mtok
               if price.cached_input_per_mtok is not None
               else price.input_per_mtok)
```

The wrong version produces no error message. It produces a dashboard that says you are saving money. The self-test catches it. Check 8 expects $0.02 for 10,000 cached tokens at a $2.00 input price. With the zero fallback, the total is $0.00. A copy of `pricing.py` with that change printed `[FAIL] unknown cached price falls back to full price` on 2026-09-17.

**The price sheet grew too.** `prices.yaml` is now schema version 3. It carries these fields per model:

- `cached_input_per_mtok`, `cache_write_per_mtok`, `cache_write_1h_per_mtok`
- `batch_multiplier`, `tier_multipliers`, `modality_multipliers`
- `min_cache_tokens`, `context_window`, `max_output`
- a `priced_on` date

The Phase 1 and Phase 2 scripts still read this file. Adding keys breaks nothing.

The `priced_on` field has a purpose. Prices change. Nobody can audit a price in your repository that has no date next to it.

**The sentence to remember:** a bill has five token classes and two multipliers. Your first meter had two classes and nothing else. The missing pieces move the number the most.

**The trap:** an overcharging meter looks conservative, but it hides information. You cannot see a saving you do not measure, and you cannot see it stop.

**Try this now:** run `python pricing.py --role deep`. The last line shows either `cached/input ratio: ...` or `cached price NOT SET for this model`. For `deep` it prints NOT SET on the current sheet. Filling in that price is your first task in this phase.

---

## 3.2 — Implicit prefix caching (automatic, invisible, and easy to lose)

Why this matters: Phase 2 explained the radix tree that lets the server reuse a prefix. This section is the billing side of the same mechanism. You do not have to ask for it. You cannot see it in the response body unless you look for it. One line of code can break it.

**The mechanism in one paragraph.** The provider hashes your prompt prefix in blocks. A later request from the same organisation may start with the same bytes. The server then reuses the stored work. It charges you a fraction of the input price for those tokens. Nothing in your code changes. Phase 2's exercise E5 measured the effect in a simulator.

### The rules, with the numbers

All figures below come from the provider documentation, read on 2026-09-12. They change. Check yours and write the date next to them.

```
┌──────────────────────┬────────────────────────┬───────────────────────────┐
│                      │ OpenAI                 │ Anthropic                 │
├──────────────────────┼────────────────────────┼───────────────────────────┤
│ turned on by         │ default, automatic     │ nothing. It is opt-in.    │
│                      │                        │ See section 3.3.          │
│ minimum prefix       │ 1,024 tokens           │ 512 to 4,096 by model     │
│ cache read price     │ 0.1x input             │ 0.1x input                │
│ cache WRITE price    │ 1.25x input            │ 1.25x (5 min) or 2x (1 h) │
│ lifetime             │ 30 minutes, sliding,   │ 5 minutes from the last   │
│                      │ on current models      │ use, or 1 hour if asked   │
│ writes per request   │ at most 4              │ at most 4 breakpoints     │
│ shared between orgs  │ no, and not across     │ no, and isolated per      │
│                      │ regional boundaries    │ workspace on most surfaces│
└──────────────────────┴────────────────────────┴───────────────────────────┘
```

**Two of those rows changed recently. Older material gets both of them wrong.**

1. **Cache writes now cost money on OpenAI too.** The price is 1.25x the uncached input rate. Caching used to be free to try. It is not free any more. A workload that writes many entries and never reads them back now loses money. Section 3.3 gives you the break-even arithmetic for this case.
2. **The discount itself changed.** Prompt caching launched in October 2024 with a **50%** discount. It is now 0.1x, which is a 90% discount. Say you put a multiplier in your cost code two years ago. That multiplier is wrong today. The error is in your favour: you under-reported your savings the whole time.

### Where the number is

You cannot see a cache hit without reading the usage object. The field path differs by API, and this catches people:

```
Chat Completions   usage.prompt_tokens_details.cached_tokens
                   usage.prompt_tokens_details.cache_write_tokens
Responses          usage.input_tokens_details.cached_tokens
                   usage.input_tokens_details.cache_write_tokens
```

A second difference matters more. It is the fact in this phase that causes the most bugs:

```
┌───────────┬──────────────────────────────────────────────────────────────┐
│ OpenAI    │ cached_tokens is INSIDE prompt_tokens.                       │
│           │ uncached = prompt_tokens - cached_tokens - cache_write_tokens│
├───────────┼──────────────────────────────────────────────────────────────┤
│ Anthropic │ cache reads and writes are NOT inside input_tokens.          │
│           │ total_input = input_tokens + cache_read + cache_creation     │
└───────────┴──────────────────────────────────────────────────────────────┘
```

Anthropic's documentation states that `input_tokens` "represents only the tokens that come after the last cache breakpoint". Say you write one summation function and use it for both providers. Then one provider's numbers will be wrong by the size of your whole system prompt. Write one adapter per provider.

`cost_meter.py` has both adapters, in `extract_usage` at `cost_meter.py:66`. It prints the shape it matched, so a mismatch cannot stay hidden.

### Measure it on your own account

```bash
python phase03_economics/cost_meter.py --replay --role cache_demo     # offline
export OPENAI_API_KEY=sk-...
python phase03_economics/cost_meter.py --model <your-model> --role cache_demo
```

The replay uses the verified gpt-5.6-terra prices. Its token counts are synthetic. The output on the author's machine on 2026-09-17, trimmed to call 2 and the summary line:

```
call 2 (warm cache)
  input       : 12,400 tokens (400 full price, 12,000 cached)
  cache hit   : 96.8% of input tokens
  naive cost  : $0.028400   <- the Phase 1 formula
  true cost   : $0.006800
  gap         : $0.021600  (76.1% overstated)

warm call is 4.18x cheaper than the cold call.
```

The same run prints two batch lines. All three per-call costs:

```
Replay, role cache_demo, per call, from the run above

  cold call, full price          ████████████████████████████████████  $0.028400
  warm call, cached              █████████                             $0.006800
  warm call, cached and batched  ████                                  $0.003400

  cold to warm: 4.18x cheaper      cold to warm and batched: 8.35x cheaper
```

The live version sends the same prompt twice and reads the real counts. Call 2 may report zero cached tokens. The script then prints a diagnosis, so you do not have to guess.

### What breaks a hit

Phase 2 gave you the rule. The match runs from token 0 forward and stops at the first difference. Here is the list of things that cause that difference. It comes from both providers' documentation.

**Content changes you expect.** Any edit to the text before the boundary breaks the hit. Examples are a timestamp, a session id, a user name, or a request id.

**Setting changes you do not expect.** On OpenAI, a change to any of these settings breaks the prefix:

- the model
- the tool definitions, including **their order**
- `parallel_tool_calls`
- the structured-output format
- `reasoning.effort`
- verbosity
- the context-management setting

On Anthropic, a change to the tool definitions breaks everything. Turning web search, citations, or the speed setting on or off breaks the system and message levels. Adding or removing an image anywhere breaks the message level.

**A serialization bug you will not guess.** Some languages randomise map key order when they produce JSON. Anthropic's documentation warns about this and names Go and Swift. Your tool definitions then serialise differently each time a process starts. Your cache hit rate then depends on which pod served the request. The fix is to force a fixed key order in the code that serialises your tool schemas.

**Truncation.** Your history can grow past the context window. If your code then trims messages from the front, every later request has a different prefix. This is Phase 2's compaction problem, from section 2.6, showing up on this phase's bill.

**Parallel fan-out at cold start.** A cache entry becomes usable only after the first response begins. Say you start ten agent calls at once, with the same new system prompt. They write ten entries and read none. With writes priced at 1.25x, that fan-out costs more than no caching at all. Warm the cache with one call first. Then fan out.

```
Ten calls with the same 12,000-token system prompt, input tokens only.
Prices from the gpt-5.6-terra row: input $2.00, write $2.50, read $0.20 per Mtok.
Steps are an order of events, not measured times.

┌─────────────────────────────────────┬──────────────────────────────────────┐
│ all ten at once                     │ one warm-up call, then nine          │
├─────────────────────────────────────┼──────────────────────────────────────┤
│ step 1  calls 1 to 10 start         │ step 1  call 1 starts                │
│         no entry exists yet         │         no entry exists yet          │
│ step 2  10 WRITES, 0 READS          │ step 2  call 1 response begins       │
│                                     │         the entry is now usable      │
│                                     │ step 3  calls 2 to 10 start          │
│                                     │         1 WRITE, 9 READS             │
├─────────────────────────────────────┼──────────────────────────────────────┤
│ 10 x 12,000 x $2.50 / 1e6 = $0.300  │ 12,000 x $2.50 / 1e6     = $0.0300   │
│                                     │ 9 x 12,000 x $0.20 / 1e6 = $0.0216   │
│                                     │ total                    = $0.0516   │
└─────────────────────────────────────┴──────────────────────────────────────┘
No caching at all: 10 x 12,000 x $2.00 / 1e6 = $0.240
```

### What it is worth in production

Two teams published measured numbers and stated their conditions.

**ProjectDiscovery.** This team runs a security-testing platform with multi-agent workflows. Each task has 20 to 40 steps. Each system prompt is over 20,000 tokens. The team moved volatile content out of the prefix. Their cache hit rate went from **7.6% to 73.7% in a single deploy**, and later to 85%. Their reported saving went from 59% to 70% of LLM cost.

```
ProjectDiscovery cache hit rate, from their weekly table

  before the reordering  ███                                         7.6%
  the week it shipped    █████████████████████████████              73.7%
  later                  ██████████████████████████████████           85%
```

Their clearest example compares two tasks with nearly the same token volume. One task ran at a 91.8% cache rate. The other ran at 3.2%. The post says the second task cost roughly **60 times** more. Hit rate alone cannot explain that. With misses at the plain input price, the average price per input token at those rates differs about 5.6x, and caching can never make it differ more than 12.5x (a 1.25x write against a 0.1x read). The post does not show where the rest comes from.

**Deriv.** A production assistant team measured an **85.8% hit rate and a 77% reduction in input-token cost**. Note their own caveat. Their dollar figures are illustrative, because their volume is confidential. The percentages are measured.

Caching also reduces latency, not only cost. TTFT is time to first token, the wait before the first output token arrives. OpenAI's cookbook reports cached requests about 7% faster at the 1,024-token minimum. At 150,000 tokens and above, it reports up to **67% faster TTFT**. This is Phase 1's TTFT lesson, now on your invoice.

**On Anthropic, caching also raises throughput.** On most models, cache-read tokens do not count toward the input tokens-per-minute rate limit. The provider gives a worked example. A limit of 2,000,000 tokens per minute with an 80% hit rate processes an effective 10,000,000 tokens per minute. If your limit is the rate limit and not the cost, caching still helps.

### One provider works differently

Google's documentation for implicit context caching says it offers **"no cost saving guarantee"**. Its explicit caching does guarantee savings, and the documentation labels it beta. Google also bills in a different way. It charges **storage by the hour**. One current model costs $0.50 per million tokens per hour. OpenAI and Anthropic charge a one-time write premium instead.

That difference changes the break-even completely. An idle cache entry costs you nothing on two providers. On the third, you pay for every hour it is stored.

**The sentence to remember:** implicit caching is free to turn on and easy to lose. Only the cached-token count in the usage object tells you it is working.

**The trap:** a prefix below the minimum is not an error. It caches nothing and returns success. Anthropic states this directly: shorter prompts cannot be cached even when marked, and no error is returned.

**Try this now:** run `python phase03_economics/cost_meter.py --replay --role deep`. The `deep` row has no cached price in the sheet. So the gap line shows `$0.000000  (0.0% overstated)`, and the warm call is `1.00x cheaper`. The last line is a WARNING that the price is missing. That is the fallback from 3.1 working as designed. It also reminds you to fill in the sheet.

---

## 3.3 — Explicit caching with cache_control (the lab Phase 1 owed you)

Why this matters: Phase 1 exercise E6 measured implicit caching. It excluded Claude models on purpose, because they need explicit breakpoints. It said this phase would cover them. This section is that lab. Explicit caching also teaches more. It shows you every decision that implicit caching hides.

**The trade.** Implicit caching picks the boundary for you, and you cannot control the lifetime. Explicit caching lets you place the boundary and buy a longer lifetime. You pay extra for that control.

### How a breakpoint works

A breakpoint is a content block that you mark with `cache_control`. That mark writes exactly one entry. The entry is a hash of the prefix that ends at that block. The system does not write entries for earlier positions.

```
system blocks                                      what gets cached

┌──────────────────────────────┐
│ tool definitions             │  ─┐
├──────────────────────────────┤   │  the entry is a hash of
│ policy text, 8,000 tokens    │   ├─ EVERYTHING up to and
│   cache_control: ephemeral   │  ─┘  including this block
├──────────────────────────────┤
│ today's date, session id     │        below the breakpoint:
└──────────────────────────────┘        never cached, and it
                                        cannot break the entry
messages: the live conversation
```

On the next request, the server hashes the prefix at your breakpoint and looks for a match. If there is no match, it walks backward one block at a time. The documented lookback limit is 20 blocks. You get at most 4 breakpoints per request. A fifth one returns HTTP 400.

**The order is fixed.** The provider builds cache prefixes in this order: tools, then system, then messages. A change at one level breaks that level and every level after it. So an edit to a tool definition breaks everything. A new user message breaks nothing above it.

### The break-even, derived

A write costs more than an uncached token. A read costs less. So explicit caching only pays if you read the entry enough times before it expires.

```
extra cost to write   = (write_rate - input_rate) x tokens
saving per read       = (input_rate - cached_rate) x tokens

reads needed to profit = (write_rate - input_rate) / (input_rate - cached_rate)
```

Put in the verified multipliers. A 5-minute write costs 1.25x input. A read costs 0.1x:

```
(1.25 - 1.00) / (1.00 - 0.10) = 0.25 / 0.90 = 0.28 reads
```

So one read already makes a profit. Now the 1-hour tier at 2x:

```
(2.00 - 1.00) / (1.00 - 0.10) = 1.00 / 0.90 = 1.11 reads
```

That means two reads. This matches the provider's own guidance. Caching pays off after one read at the 5-minute duration. It pays off after two reads at the 1-hour duration. Derive it yourself anyway. The multipliers change, and the formula does not.

```
reads needed before the entry pays for itself

  5-minute write, 1.25x   ███████                              0.28  → read 1
  1-hour write,   2.00x   ████████████████████████████         1.11  → read 2
```

In live mode, `cache_control_lab.py` prints this line before the first turn. It computes the numbers from your own price sheet, at `cache_control_lab.py:412`:

```
break-even: the write costs 1.25x input, each read saves 90%. You need 0.28 reads to profit, so 1 read(s) in practice.
```

This line was not run here, because it needs an API key. It is inferred from the code and the `claude` price row. `--explain` does not print it.

**When the 1-hour tier wins.** A 2x write pays when the gaps between your calls are longer than 5 minutes. Examples are a human conversation with pauses, a batch job, or a nightly agent. It does not pay for a fast tool-calling loop. In that loop, the 5-minute entry never expires anyway.

### Reading the usage object

```
usage.input_tokens                  ONLY the tokens after the last breakpoint
usage.cache_read_input_tokens       tokens served from the entry, at 0.1x
usage.cache_creation_input_tokens   tokens written into the entry, at 1.25x or 2x
usage.cache_creation.ephemeral_5m_input_tokens    the split, by TTL
usage.cache_creation.ephemeral_1h_input_tokens
```

TTL is time to live, the lifetime of a cache entry. The identity to remember:

```
total_input_tokens = cache_read_input_tokens + cache_creation_input_tokens + input_tokens
```

Say a team shows `input_tokens` on a dashboard as "input tokens". For a heavily cached agent, that number is near zero, and nobody questions it. A public issue against the Langfuse observability product documents this bug:

- The true cost of the agent run was $0.522.
- The dashboard reported $0.238, which is 45.5% of the true cost.
- The instrumentation sent neither cache reads nor cache writes.
- The dashboard logged the input as **20 tokens**.

Twenty tokens for a multi-turn agent run is clearly wrong. It stayed on a dashboard unnoticed. The dashboard showed it in the same way as a correct number.

### Run the lab

```bash
python phase03_economics/cache_control_lab.py --explain          # no key needed
export ANTHROPIC_API_KEY=sk-ant-...
python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5
python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5 --no-cache
python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5 --break-it
```

Turn 1 costs **more** than the control run, because you paid the write premium. From turn 2, the cost per turn drops a lot. The script prints a running total. You can see the exact turn where the cached run becomes cheaper than the control.

`--break-it` puts a timestamp block **above** the breakpoint. Every turn then reports a cache write and no read. You pay the premium every time and never get the discount. This is the most expensive mistake in explicit caching. It is the same mistake as Phase 0's Story 1, in a different API.

### Rules that are easy to miss

**The silent no-op.** The provider does not cache a prefix below the model's minimum, and it returns no error. The minimums vary a lot, from 512 tokens on some models to 4,096 on others. The price sheet now carries `min_cache_tokens` per model. The lab warns you before it sends any request, at `cache_control_lab.py:401`.

**Batch jobs need the long tier.** The provider guidance is direct. A batch can take longer than 5 minutes. So use the 1-hour duration for shared context inside a batch. One feature does not work in a batch. You cannot pre-warm a cache with a zero-token generation there. The entry would expire before the follow-up request ran.

**The discounts stack.** Anthropic states that the batch discount and the caching discounts combine. OpenAI's batch page does **not** document the same claim, so do not assume it. You can check it with one experiment. Submit a batch with a repeated long prefix. Then read the cached-token count in the output file.

**The sentence to remember:** explicit caching is a purchase, not a setting. Compute the break-even in reads before you place a breakpoint.

**The trap:** a volatile block above the breakpoint turns every request into a cache write. You then pay 1.25x for input that would cost 1x with caching turned off.

**Try this now:** run `python phase03_economics/cache_control_lab.py --explain --break-it`. Read the block order it prints. The timestamp block comes first, and the block with `cache_control` comes second. Before you run anything live, predict what the `written` and `read` columns will show on turn 3.

---

## 🧪 Hands-on lab — part A

Setup: `cd ~/Desktop/project/code/study-material/inference-internals/code && uv sync`.

**Run status.** The author first ran every offline command on 2026-09-12. A review re-ran them on 2026-09-17, and the Expected lines below match that run. No API key was available, so E4 to E8 did not run against a live provider. The review checked their flags against each script's `--help`.

- [ ] **E1 (offline).** Test the money arithmetic before you trust it.
  - Run: `python pricing.py --self-test`
  - Expected: 13 checks pass, and the last line is `all checks passed`. One check is "unknown cached price falls back to full price". A `WARNING` line about tier `mystery` also appears. That warning is expected, because one check uses an unknown tier on purpose.
  - Then break it on purpose. Open `pricing.py` at line 164. Change the fallback to `0.0`, and run the test again. That check now fails and names the mistake you made. Change it back.
  - Teaches: a cost module is software with a correctness property. It is more than a one-line formula.

- [ ] **E2 (offline).** Read your own price sheet.
  - Run: `python pricing.py --role deep` then `python pricing.py --role cheap`
  - Expected: a `Price(...)` row for each. Each row ends with `cached_input_per_mtok=None`. The next line is `cached price NOT SET for this model`. A row with a cached price prints `cached/input ratio: ...` instead. Try `python pricing.py --role cache_demo` to see `0.100`.
  - Then edit `prices.yaml`. Replace both models with the ones you use. Fill in every field you can find on the provider's pricing page. Set `priced_on` to today. If you cannot find a field, leave it out. Do not guess it.
  - Teaches: the price sheet is the input to every number in this phase. A guessed price produces a wrong answer that looks certain.

- [ ] **E3 (offline).** See the gap your Phase 1 meter was hiding.
  - Run: `python phase03_economics/cost_meter.py --replay --role cache_demo`
  - Expected: the cold call shows a gap of `$0.000000`. The warm call shows the naive formula overstating by 76.1%. The warm call is 4.18x cheaper than the cold call. The batch lines show $0.003400 for the warm batched call, 8.35x cheaper than the cold call.
  - Then run it with `--role deep` and with `--role cheap`. Both show a gap of zero and `1.00x cheaper`, then a WARNING line. Neither row has a cached price, so the ratio is 1.00 by construction. The batch lines still halve the cost, for example $0.027200 to $0.013600 for `deep`.
  - Teaches: the size of the saving, before you spend anything to measure it live. It also shows that a missing price hides the saving completely.

- [ ] **E4 (UNVERIFIED against a live provider).** See a real cache hit on your own account.
  - Run: `python phase03_economics/cost_meter.py --model <your-model> --role cache_demo`
  - Expected: call 1 reports 0 cached tokens. Call 2 reports most of the 12,000-token prefix as cached. The gap column shows the naive formula overstating by more than half.
  - If call 2 also reports 0: read the diagnosis the script prints. The usual causes are a prefix below the minimum, or too long a pause between calls. A gateway that drops the details object is a third cause.
  - Costs at most: about $0.05.
  - Teaches: the cached-token count is the only proof that caching works.

- [ ] **E5 (break-it, UNVERIFIED against a live provider).** Break the hit with one line.
  - Edit `build_prompt` at `cost_meter.py:56`. Put the current timestamp at the start of the returned prompt, at position 0. Run E4 again.
  - Expected: call 2 now reports 0 cached tokens, and the true cost equals the naive cost. You changed about 25 characters and lost the whole discount.
  - Then move the timestamp to the END of the prompt and run it again. The hit comes back.
  - Teaches: Phase 0's Story 1, on your own bill, in two minutes. Remove your edit afterwards.

- [ ] **E6 (break-it, UNVERIFIED against a live provider).** Go below the minimum and get no error.
  - Run: `python phase03_economics/cost_meter.py --model <your-model> --role cache_demo --prefix-tokens 400`
  - Expected: both calls succeed, and both report 0 cached tokens. Nothing in the output says why. A prefix below the documented minimum does nothing and raises no error.
  - Then raise it to 1,200 and watch the hit appear.
  - Teaches: the lack of an error does not prove that a feature works.

- [ ] **E7 (UNVERIFIED against a live provider).** Use explicit caching, and find the break-even turn.
  - Run offline first: `python phase03_economics/cache_control_lab.py --explain`. Read the block order and the usage fields it names.
  - Then: `python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5`. Run it again with `--no-cache`.
  - Expected: the script prints the break-even in reads before the first turn. Turn 1 of the cached run costs MORE than the control, because you paid the write premium. By turn 2 or 3, the cached run's running total drops below the control's. Write down which turn.
  - Costs at most: about $0.10 for both runs.
  - Teaches: explicit caching is a purchase with a payback period. It is not a switch.

- [ ] **E8 (break-it, UNVERIFIED against a live provider).** Pay the premium every turn and never collect.
  - Run: `python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5 --break-it`
  - Expected: every turn shows a non-zero `written` column and a zero `read` column. You paid 1.25x input on every turn. This run costs more than a run with caching turned off.
  - Teaches: a volatile block above the breakpoint reverses the benefit of the feature. Compare this total with the `--no-cache` control from E7, and write down the difference.

---

## 🔍 Check it yourself — questions against the course code

This course has no anchor repository, so these questions target the course code. The last one works on any repository.

1. Open `pricing.py` at line 156, the `cost` function. Line 164 chooses `cached_rate`. Explain in one sentence why it falls back to `price.input_per_mtok` and not to `0.0`. Then name the wrong conclusion the zero version would produce on a dashboard.

2. Open `prices.yaml`. The `gpt-4.1-mini` and `gpt-4.1` rows have no `cached_input_per_mtok`. That is deliberate. Read the comment block above those two rows. Then answer two questions. What does `pricing.py` charge for a cached token on those two models? Is that error in the safe direction or the dangerous one?

3. Open `phase03_economics/cost_meter.py` at line 66, `extract_usage`. It has two separate code paths that never share a summation. Use only the code to answer. Which provider includes cached tokens inside its base input count? Which one reports them separately? Then find the line that returns the name of the matched shape, so a mismatch cannot stay hidden.

4. In any repository you own that calls an LLM, find where the code reads the response usage. Answer three questions:
   - Does it record a cached-token count?
   - Does it record cost per request, or only tokens?
   - Would any code notice if the cached count went to zero tomorrow?

   Three honest "no" answers are the normal starting point. They are Phase 0's Story 1, waiting to happen.

---

## ✅ Checkpoint 3A — answer in your own words

1. Show the math. A model has these prices per million tokens: input $2.00, cached input $0.20, cache writes $2.50, output $12.00. Your agent step sends 20,000 input tokens. Of those, 18,000 hit the cache. The step generates 400 output tokens. (a) Compute the true cost. (b) Compute what the Phase 1 two-price formula would report. (c) State how many times higher the old meter's number is. (d) Your finance team uses the old number to set customer prices. Name the business error that this creates.

2. A colleague says: "We turned on prompt caching and our costs did not move. So caching does not work for our workload." Give three separate, specific causes of that observation. For each cause, name the one number you would check to confirm or rule it out.

3. Show the math, then decide. A provider charges 2x input for a one-hour cache write, 1.25x for a five-minute write, and 0.1x for a read. (a) Derive the number of reads needed before the one-hour tier makes a profit. (b) Your agent makes one call every 12 minutes for an hour. Which tier do you pick, and why? (c) Your agent makes one call every 20 seconds for two minutes, then stops. Which tier do you pick, and why is the answer different?

4. This is broken. Your cost dashboard reports $0.24 for an agent run. The provider billed $0.52. The dashboard shows 20 input tokens and 13,545 output tokens. The run had many turns and a large system prompt. (a) Name the cause. (b) Explain why 20 input tokens should have looked wrong to any reader. (c) Name the two missing usage fields. (d) Say why this kind of bug gets through code review.

5. Walk me through what happens. Your agent gets a burst of 10 identical requests at once, at cold start. Each carries the same 12,000-token system prompt. The provider charges 1.25x for cache writes. (a) Trace what the cache does across those 10 requests. (b) Compare the total input cost with the same 10 requests with caching turned off. (c) State the one change to your call pattern that fixes it, and its latency cost.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) Uncached input is 20,000 - 18,000 = 2,000 tokens. 2,000 x $2.00 / 1e6 = $0.004. Cached input is 18,000 x $0.20 / 1e6 = $0.0036. Output is 400 x $12.00 / 1e6 = $0.0048. The true total is $0.0124.
   (b) Naive: 20,000 x $2.00 / 1e6 + $0.0048 = $0.04 + $0.0048 = $0.0448.
   (c) $0.0448 / $0.0124 = about 3.6x.
   (d) You set prices against a cost 3.6x higher than your real cost. You lose deals you could have won. You also cannot explain your own margin when someone checks the invoice.

2. Here are three causes, each with the number that confirms it.
   - The prefix is below the minimum. Nothing caches, and no error appears. Check the cached-token count. It is exactly 0 on every call.
   - Something volatile sits early in the prompt, so every request is cold. The cached count is also 0. To tell this apart from the first cause, make the prefix longer and see whether anything changes.
   - The saving is real, but your meter cannot see it. Check whether your code reads the cached-token field at all. If it does not, your cost number can never move.
   - A fourth answer is also correct. Writes cost 1.25x. A workload with many writes and few reads does not save money.

3. (a) (2.00 - 1.00) / (1.00 - 0.10) = 1.11, so two reads.
   (b) With a 12-minute gap, a five-minute entry always expires before the next call. That tier gives you a write every time and no reads. The one-hour tier gives one write and four reads within the hour. Four reads clear the two-read break-even. Pick one hour.
   (c) Calls 20 seconds apart never let a five-minute entry expire. So the cheaper 1.25x write is already reused. The extra 0.75x for the longer tier buys nothing. Pick five minutes.

4. (a) The instrumentation did not send cache-read or cache-write tokens. So the tool recomputed the cost from partial counts.
   (b) On that provider, `input_tokens` counts only the tokens after the last cache breakpoint. A multi-turn run with a large system prompt cannot have only 20 real input tokens. The tool read the field as if it meant total input.
   (c) `cache_read_input_tokens` and `cache_creation_input_tokens`.
   (d) The wrong number looks plausible. It comes through the same code path as correct numbers. Nothing raises an error. Only a comparison with the provider's own cost report catches it.

5. (a) A cache entry becomes usable only after the first response begins. All 10 requests start before any entry exists. So all 10 write, and none read.
   (b) With writes at 1.25x, the 10 requests cost 1.25 times the cost with caching turned off. For the 12,000-token prompt at $2.00 input, that is $0.300 against $0.240. Caching made this burst more expensive.
   (c) Send one warm-up call. Wait until its response starts. Then send the other 9 against the warm entry. The cost is the latency of one extra round trip at the start of the burst.

</details>

---

## References & Further Learning

Every URL below was fetched and checked on 2026-09-12. Some pages blocked automated fetching, and some claims could not be confirmed. The entry says so in those cases. Prices and limits in this area change faster than anything else in the course. Treat every number as a dated value.

### Must-read before the lab

- **OpenAI prompt caching guide** — https://developers.openai.com/api/docs/guides/prompt-caching
  The primary source for section 3.2. The older `platform.openai.com` path now redirects here, so cite this one. Focus on the prompt-cache-options section and the invalidation list.
  Verified numbers: a 1,024-token minimum, and a 30-minute sliding window on current models. Reads cost 0.1x input, **writes cost 1.25x**, and a request makes at most four writes. Caches are not shared across organisations or regional processing boundaries.

- **Anthropic prompt caching** — https://platform.claude.com/docs/en/build-with-claude/prompt-caching
  The primary source for section 3.3. It is the better of the two documents, because it describes the lookup algorithm and not only the API. Focus on how breakpoints work, the minimum-length table, the invalidation table, and the one-hour duration section.
  Verified facts: one entry per breakpoint, a 20-block lookback, at most 4 breakpoints, and the order tools, system, messages. Minimums run from 512 to 4,096 tokens, and below the minimum **nothing caches and no error is returned**. Reads cost 0.1x, five-minute writes 1.25x, one-hour writes 2x. The page states the break-even directly: one read for the five-minute tier, two for the one-hour tier.

- **Anthropic rate limits** — https://platform.claude.com/docs/en/api/rate-limits
  Read one fact from this page. On most models, only uncached input tokens count toward the input tokens-per-minute limit. Section 3.2 quotes the page's worked example of 2,000,000 tokens per minute at an 80% hit rate.

### Deep dives

- **Prompt Caching 201** — https://developers.openai.com/cookbook/examples/prompt_caching_201
  The clearest latency evidence available, and the source of section 3.2's 7% and 67% figures. It also reports one coding customer's hit rate. It rose from 60% to 87% after the customer adopted a cache key.
  Honest note: the page describes the workload only as "coding". It names no model for that improvement.

- **How We Cut LLM Costs by 59% With Prompt Caching, ProjectDiscovery, 10 April 2026** — https://projectdiscovery.io/blog/how-we-cut-llm-cost-with-prompt-caching
  The best production write-up on this topic, because it states its measurement method. The team derived effective per-token rates from real spend. They compared those rates with the standard-rate cost of the same volume. Focus on the weekly hit-rate table.
  Conditions: an autonomous security-testing platform, 20 to 40 LLM steps per task, and system prompts over 20,000 tokens per agent. Section 3.2 quotes its hit rates, its 59% to 70% savings, and its 60x two-task comparison, which is larger than hit rate alone can explain.

- **How prompt caching cut our production AI agent input costs by 77%, Deriv, 23 July 2026** — https://derivai.substack.com/p/prompt-caching-production-ai-agent-costs
  A second independent production measurement. Section 3.2 quotes its 85.8% hit rate and 77% saving.
  Honest note, from the author: the dollar figures are illustrative, because production volume is confidential. Use the percentages, not the dollars.

- **Google context caching** — https://ai.google.dev/gemini-api/docs/generate-content/caching
  Read it for the contrast in section 3.2. Implicit caching has "no cost saving guarantee", and storage is billed **by the hour**.

- **Batch APIs** — https://developers.openai.com/api/docs/guides/batch and https://platform.claude.com/docs/en/build-with-claude/batch-processing
  Both providers price batch at 50% of synchronous rates. Focus on the limits and the expiry behaviour, which differ. When a batch expires, one provider returns and bills the completed requests. The other does not bill expired requests. One of the two states that batch and caching discounts combine. It recommends the one-hour cache tier inside batches. The other does not document the interaction at all, so do not assume it.

### Cost accounting and alerting

- **OpenTelemetry GenAI semantic conventions** — https://github.com/open-telemetry/semantic-conventions-genai
  The attribute registry is at `docs/registry/attributes/gen-ai.md` in that repository. There is no released version, so cite a commit. The commit checked here is dated 2026-09-10.
  What to take from it: all 118 attributes have development stability. Cached tokens are `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_write.input_tokens`. Reasoning tokens are `gen_ai.usage.reasoning.output_tokens`. Detailed attributes are subsets of the totals.
  What is missing: there is **no cost attribute**, and no batch attribute. Open pull request 443 proposes `gen_ai.usage.cost.amount`, `.currency` and `.source`. Use those names now.
  The trap: the standard token metric has only an input-or-output dimension. With caching on, you cannot compute spend from it. Use span attributes.

- **Provider usage and cost APIs** — https://platform.claude.com/docs/en/manage-claude/usage-cost-api
  Read it to learn what the provider cannot do for you. Both major providers report cost in daily buckets. This one documents about five minutes of lag on token data. It returns amounts as decimal strings in the lowest currency unit. No documented lag was found for the other. So you meter locally and reconcile daily.

- **Spend limits** — https://developers.openai.com/api/docs/guides/spend-limits and https://developers.cloudflare.com/ai-gateway/features/spend-limits/
  The first page covers alerts, hard limits, and their error codes. It states twice that "Enforcement is not instantaneous, so recorded spend can slightly exceed the configured amount".
  The second offers budgets per provider, model, or metadata value, and can fall back to a cheaper model. It admits that "a burst of concurrent requests can briefly exceed the limit".
  The shared lesson: every provider-side control enforces against spend data that is already out of date.

- **Budgets and rate limits in a gateway** — https://docs.litellm.ai/docs/proxy/users
  The only documented pre-call budget mechanism found. It reserves the worst-case cost from `max_tokens`. It rejects a request that would go over budget. It then settles to the actual cost. Its documented weak spots: a cross-pod counter can be stale after a restart, and a fail-closed mode rejects with 503. It cannot price a batch submission, because the request carries a file reference, not prompts.

- **Update on Security at METR, 31 August 2026** — https://metr.org/blog/2026-08-31-security-update/
  The closest thing to a primary incident account in this area. An exposed internal application used about $600,000 of API credits over about three weeks. The post gives three reasons that detection failed, and they are the main point of section 3.5:
  1. High token volume looked normal.
  2. The dashboard did not show the relevant signal.
  3. No spend ceiling existed, because the tokens were free.

  Read it first, before the rest of section 3.5.

- **Token Budgets: An Empirical Catalog of 63 LLM-Agent Budget-Overrun Incidents, June 2026** — https://arxiv.org/abs/2606.04056
  The authors screened 167 candidates and kept 63, across 21 frameworks. Inter-rater agreement on inclusion was 0.837. The largest cause clusters are retry loops and missing cost observability. Its one-sentence conclusion is the one to quote. It found no case where a budget overrun was prevented before a user paid for it.
  Honest note: this is a single-author preprint with no peer review. Agreement on its mechanism clusters is much weaker, at 0.44. Cite the total counts, not individual entries.

- **A cost dashboard that was wrong by more than half** — https://github.com/langfuse/langfuse/issues/13807
  A fully instrumented case that you can reproduce, and the source of section 3.3's $0.522 and $0.238 figures. The issue body gives $0.52231845 and $0.237606, rechecked on 2026-09-17. That ratio is 45.5%. Read it as the real example behind the warning about `input_tokens`.

### Not verified, stated so you do not repeat it

- OpenAI's batch page does **not document** whether batch requests hit the prompt cache. Anthropic documents its equivalent claim. Section 3.3 gives the one-experiment check.
- A widely shared "$47,000 runaway bill" story traces only to secondary posts. Their own figures contradict the headline. There is no first-party source. The same is true of most large dollar figures in this topic area.
- A post is often cited for this claim: a vendor treats a hit rate below 90% as an incident. The claim is not on the vendor's site. Treat it as misattributed.

---

## Cheatsheet — part A

```
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
  minimum prefix 1,024 tokens (OpenAI) | 512-4,096 by model (Anthropic)
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
  volatile block ABOVE the breakpoint = a write every turn, forever

WHAT BREAKS A HIT
  any byte change before the boundary | tool definitions AND their ORDERING
  parallel_tool_calls | structured-output format | reasoning effort | verbosity
  adding or removing an image | non-deterministic JSON key order (Go, Swift)
  front-truncating history | a different org, workspace, or region

THE COMMANDS (part A)
  pricing.py --self-test                     → the money arithmetic, 13 checks
  pricing.py --role deep                     → read your own price sheet
  cost_meter.py --replay --role cache_demo   → the size of the saving, offline
  cost_meter.py --model X --role cache_demo  → a real cache hit, live
  cache_control_lab.py --explain             → the request shape, offline
  cache_control_lab.py --model X --role claude          → explicit caching
  cache_control_lab.py --model X --role claude --break-it → pay forever
```

Part B covers routing cascades, batch APIs, and per-request cost alerting. That alerting catches a cache regression within ten requests, not four months.

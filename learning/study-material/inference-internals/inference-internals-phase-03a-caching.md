# Phase 3A — The bill and the cache (the phase that pays for the course)

Phase 1 taught you to measure one request. Phase 2 taught you what the server does with it. This phase is about the bill, and it starts with a confession about the meter you built in Phase 1.

That meter is wrong. It prices every input token at the full input price. Real providers bill input tokens in several classes, and the cheapest class costs a tenth of the most expensive. A meter that cannot see the classes reports a number that is too high. That is not a safe error. It hides the savings you already earn, and it hides the moment you stop earning them.

Phase 1's codebase-anchor question asked you to find that gap. Phase 0's Story 1 described what happens when nobody does: a team paid full price on every agent step for four months, because a timestamp sat at the top of their prompt and their cache never matched.

Phase 3 is split into two documents because it covers five separate topics and pays three debts from earlier phases. This is part A.

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

After part A you can read a provider's real invoice from the `usage` object, lay out a prompt so the cache hits, prove the hit rate with a number, and decide whether explicit caching pays for itself from your own break-even arithmetic.

Time: 1.5 to 2 hours. Three of the four scripts run with no API key.

Setup:

```
cd ~/Desktop/project/code/study-material/inference-internals/code
pip install -e .          # or: uv sync   (Phase 3 adds the anthropic package)
python pricing.py --self-test
```

That last command must print "all checks passed" before you start. Everything here computes money, so the arithmetic gets tested first.

---

## 3.1 — The five token classes, and two multipliers (why your meter overcharges)
Why this matters: you cannot tune a bill you cannot read. And you cannot read this bill with two numbers.

Phase 1's formula was:

```
cost = input_tokens x input_price + output_tokens x output_price
```

Here is what a real request can contain instead:

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

Three of those five did not exist in your Phase 1 meter. The result is a formula that reports a number larger than your invoice.

### Two more axes that are not token classes at all

The table above splits tokens by how they were processed. Two other things change the same invoice without changing any token count, and a meter that ignores them is wrong in both directions.

**The service tier multiplies the whole request.** Batch is the tier you already met, at half price. Providers also sell tiers in the other direction: a slower tier priced below standard, and a faster, higher-priority tier priced above it. The tier applies to every class at once, so it is a multiplier rather than a price.

Two practical consequences. First, the tier appears in the usage object on at least one provider, as a `service_tier` field, so you can record what you were actually charged rather than what you asked for. Second, and this catches finance teams: on one provider the priority tier uses a different billing model and **is excluded from the cost-reporting endpoint entirely**. You must read the usage endpoint instead. A reconciliation job that queries only cost will silently under-count.

There is a third multiplier in the same family. At least one provider charges 1.1x for pinning inference to a specific region. That applies to cached reads and writes as well as to fresh input.

**Modality changes the price of an input token.** Image and audio inputs are converted to tokens, and those tokens are frequently priced above text tokens. They are reported separately, in nested fields such as `image_tokens` and `audio_tokens` inside the same details object that carries the cached count.

Here is the rule that matters, and it is the same rule the OpenTelemetry conventions state for their attributes:

```
  the detailed counts are SUBSETS of the total, never additions to it

  usage.prompt_tokens                    300   ← the total you are billed on
    prompt_tokens_details.text_tokens    100   ┐
    prompt_tokens_details.image_tokens   200   ├ these SUM to the total
    prompt_tokens_details.cached_tokens   40   ┘ and cached overlaps them

  WRONG:  total = prompt_tokens + image_tokens        (double counts)
  RIGHT:  total = prompt_tokens
          image_tokens tells you WHICH of them cost more
```

A multimodal cost meter that adds the nested counts to the total reports roughly double the real bill. `pricing.py` models the surcharge rather than the price, so an image token is charged the text rate once and then the extra on top. Its self-test proves that arithmetic:

```
  [ok ] image surcharge adds only the EXTRA
  [ok ] no surcharge when the model has no image price
  [ok ] flex tier halves the whole request
  [ok ] unknown tier prices at the standard rate
```

That last check is the design rule from earlier in this section, applied again. An unknown tier prices at the **standard** rate and prints a warning. It never guesses a discount, because a guessed discount is an error you do not notice.

**Why an overcharge is still a bug.** An estimate that is too high feels safe. It is not, for two reasons.

First, it hides your own wins. If caching already cuts your bill by half and your meter cannot see it, you cannot prove the work was worth doing, and you cannot tell when it stops working.

Second, it breaks every comparison you build on top. A routing decision between two models is a ratio. If one model caches and the other does not, an overcharging meter compares them on the wrong basis and picks the wrong model.

**The fix, as code.** Phase 3 ships `pricing.py`, one module that every later script imports. It has exactly one job: turn a token split into money.

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

Verify it on your machine:

```
python pricing.py --self-test
```

One design decision in that module is worth copying into your own code. When the price sheet does not define a cached price, the module falls back to the **full** input price, not to zero:

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

The wrong version produces no error message. It produces a dashboard that says you are saving money.

**The price sheet grew too.** `prices.yaml` is now schema version 3. It carries `cached_input_per_mtok`, `cache_write_per_mtok`, `cache_write_1h_per_mtok`, `batch_multiplier`, `tier_multipliers`, `modality_multipliers`, `min_cache_tokens`, `context_window`, `max_output`, and a `priced_on` date per model. The Phase 1 and Phase 2 scripts still read it, because adding keys breaks nothing.

The `priced_on` field is not decoration. Prices change, and a number in your repository with no date attached is a number nobody can audit.

**The sentence to remember:** a bill has five token classes and two multipliers, your first meter had two classes and nothing else, and the pieces it was missing are exactly the ones that move the number most.

**The trap:** an overcharging meter looks conservative and behaves like a blindfold. You cannot see a saving you do not measure, and you cannot see it stop.

**Try this now:** run `python pricing.py --role deep` and read the `cached/input ratio` line. If it prints that the cached price is not set, that is your first task in this phase.
---

## 3.2 — Implicit prefix caching (automatic, invisible, and easy to lose)

Why this matters: Phase 2 explained the radix tree that makes prefix reuse possible on the server. This section is the commercial side of the same mechanism. You do not have to ask for it, you cannot see it in the response body unless you look, and you can destroy it with one line of code.

**The mechanism in one paragraph.** The provider hashes your prompt prefix in blocks. If a later request from the same organisation starts with the same bytes, the server reuses the stored work and charges you a fraction of the input price for those tokens. Nothing in your code changes. Phase 2's exercise E5 measured the effect in a simulator. This is the real thing.

### The rules, with the numbers

All figures below were read from the provider documentation on 2026-09-12. They change. Check yours and write the date next to them.

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

**Two of those rows are recent changes, and older material gets both wrong.**

First, **cache writes now cost money on OpenAI too**, at 1.25x the uncached input rate. Caching used to be free to try. It is not any more, and a workload that writes many entries it never reads back now loses money. Section 3.3 gives you the break-even arithmetic for exactly this.

Second, the discount itself moved. When prompt caching launched in October 2024 the announcement offered a **50%** discount. It is now 0.1x, which is 90%. A multiplier hardcoded in your cost code two years ago is wrong today, in your favour, which means you under-reported your savings the whole time.

### Where the number actually is

You cannot see a cache hit without reading the usage object. The field path differs by API, and this catches people:

```
Chat Completions   usage.prompt_tokens_details.cached_tokens
                   usage.prompt_tokens_details.cache_write_tokens
Responses          usage.input_tokens_details.cached_tokens
                   usage.input_tokens_details.cache_write_tokens
```

There is a second difference that matters more, and it is the single most bug-prone fact in this phase:

```
┌───────────┬──────────────────────────────────────────────────────────────┐
│ OpenAI    │ cached_tokens is INSIDE prompt_tokens.                       │
│           │ uncached = prompt_tokens - cached_tokens - cache_write_tokens│
├───────────┼──────────────────────────────────────────────────────────────┤
│ Anthropic │ cache reads and writes are NOT inside input_tokens.          │
│           │ total_input = input_tokens + cache_read + cache_creation     │
└───────────┴──────────────────────────────────────────────────────────────┘
```

Anthropic's own documentation states that `input_tokens` "represents only the tokens that come after the last cache breakpoint". If you write one summation function and point it at both providers, one of them will be wrong by the size of your entire system prompt. Write an adapter per provider. `cost_meter.py` has both, in `extract_usage`, and it prints which shape it matched so a silent mismatch cannot hide.

### Measure it on your own account

```
python phase03_economics/cost_meter.py --replay --role cache_demo     # offline
export OPENAI_API_KEY=sk-...
python phase03_economics/cost_meter.py --model <your-model> --role cache_demo
```

The replay output on this machine, with the verified gpt-5.6-terra prices:

```
call 2 (warm cache)
  input       : 12,400 tokens (400 full price, 12,000 cached)
  cache hit   : 96.8% of input tokens
  naive cost  : $0.028400   <- the Phase 1 formula
  true cost   : $0.006800
  gap         : $0.021600  (76.1% overstated)

warm call is 4.18x cheaper than the cold call.
```

The live version sends the same prompt twice and reads the real counts. If call 2 reports zero cached tokens, the script prints a diagnosis rather than leaving you guessing.

### What breaks a hit

Phase 2 gave you the rule: the match runs from token 0 forward and stops at the first difference. Here is the concrete list of things that cause that difference, taken from both providers' documentation.

**Content changes you expect:** any edit to the text before the boundary, including a timestamp, a session id, a user name, or a request id.

**Setting changes you do not expect.** On OpenAI, changing any of these invalidates the prefix: the model, the tool definitions including **their ordering**, `parallel_tool_calls`, the structured-output format, `reasoning.effort`, verbosity, and the context-management setting. On Anthropic, changing tool definitions invalidates everything, and toggling web search, citations, or the speed setting invalidates the system and message levels. Adding or removing an image anywhere invalidates the message level.

**A serialization bug you will never guess.** Anthropic's documentation warns that some languages randomise map key order when producing JSON, and names Go and Swift. Your tool definitions then serialise differently on each process start, and your cache hit rate quietly depends on which pod served the request. The fix is to force deterministic key order in whatever serialises your tool schemas.

**Truncation.** When your history grows past the window and your code trims from the front, every subsequent request has a different prefix. That is Phase 2's compaction problem meeting this phase's bill.

**Parallel fan-out at cold start.** A cache entry only becomes usable after the first response begins. Firing ten agent calls at once with the same fresh system prompt writes ten entries and reads none. With writes priced at 1.25x, that fan-out costs more than not caching at all. Warm the cache with one call, then fan out.

### What it is worth in production

Two teams published measured numbers with their conditions stated.

A security-testing platform running multi-agent workflows, 20 to 40 steps per task, with system prompts over 20,000 tokens, moved its cache hit rate from **7.6% to 73.7% in a single deploy**, and later to 85%. The change was moving volatile content out of the prefix. Their reported saving went from 59% to 70% of LLM cost. Their sharpest illustration is two tasks of nearly identical token volume: one ran at a 91.8% cache rate and the other at 3.2%, and the second cost roughly **60 times** more.

A production assistant team measured an **85.8% hit rate and a 77% reduction in input-token cost**. Note their own caveat: their dollar figures are illustrative because volume is confidential. The percentages are measured.

Caching also buys latency, not only money. OpenAI's cookbook reports cached requests being about 7% faster at the 1,024-token minimum and up to **67% faster time to first token at 150,000 tokens and above**. That is Phase 1's TTFT lesson arriving on your invoice.

**And on Anthropic it buys throughput.** Cache-read tokens do not count toward the input tokens-per-minute rate limit on most models. The provider's own worked example: a 2,000,000 token-per-minute limit with an 80% hit rate processes an effective 10,000,000 tokens per minute. If you are rate limited rather than cost limited, caching is still the fix.

### One provider works differently

Google's implicit context caching carries a sentence worth quoting exactly: it offers **"no cost saving guarantee"**. Its explicit caching does guarantee savings and is documented as beta. It also bills differently from both others, charging **storage by the hour**, for example $0.50 per million tokens per hour on one current model. OpenAI and Anthropic charge a one-time write premium instead. That changes the break-even completely: an idle cache entry costs you nothing on two providers and rent on the third.

**The sentence to remember:** implicit caching is free to turn on and easy to lose, so the only number that tells you it is working is the cached-token count in the usage object.

**The trap:** a prefix below the minimum is not an error. It caches nothing and returns success. Anthropic states this explicitly: shorter prompts cannot be cached even when marked, and no error is returned.

**Try this now:** run `python phase03_economics/cost_meter.py --replay --role deep`. The `deep` row has no cached price in the sheet, so the gap shows as zero. That is the fallback from 3.1 doing its job, and it is your reminder to fill the sheet in.
---

## 3.3 — Explicit caching with cache_control (the lab Phase 1 owed you)

Why this matters: Phase 1 exercise E6 measured implicit caching and excluded Claude models on purpose, with a note that they need explicit breakpoints and that this phase would cover it. This is that lab. It is also the better teacher, because explicit caching makes every decision visible that implicit caching hides.

**The trade in one line.** Implicit caching decides the boundary for you and you cannot control the lifetime. Explicit caching lets you place the boundary and buy a longer lifetime, and charges you for the privilege.

### How a breakpoint actually works

You mark one content block with `cache_control`. That writes exactly one entry: a hash of the prefix ending at that block. The system does not write entries for earlier positions.

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

On the next request the server hashes the prefix at your breakpoint and looks for a match. If there is none, it walks backward one block at a time, up to a documented lookback of 20 blocks. You get at most 4 breakpoints per request, and asking for a fifth returns a 400.

**The order is fixed.** Cache prefixes are built in the order tools, then system, then messages. A change at one level invalidates that level and every level after it. So a tool-definition edit invalidates everything, and a new user message invalidates nothing above it.

### The break-even, derived rather than quoted

A write costs more than an uncached token. A read costs less. So explicit caching is a bet that you will read the entry enough times before it expires.

```
extra cost to write   = (write_rate - input_rate) x tokens
saving per read       = (input_rate - cached_rate) x tokens

reads needed to profit = (write_rate - input_rate) / (input_rate - cached_rate)
```

Put the verified multipliers in. A 5-minute write costs 1.25x input and a read costs 0.1x:

```
(1.25 - 1.00) / (1.00 - 0.10) = 0.25 / 0.90 = 0.28 reads
```

So a single read already profits. Now the 1-hour tier at 2x:

```
(2.00 - 1.00) / (1.00 - 0.10) = 1.00 / 0.90 = 1.11 reads
```

Two reads. That matches the provider's own published guidance exactly: caching pays off after one cache read at the 5-minute duration and after two at the 1-hour duration. Deriving it yourself matters, because the multipliers change and the formula does not.

`cache_control_lab.py` prints this line before every run, computed from your own price sheet:

```
break-even: the write costs 1.25x input, each read saves 90%.
You need 0.28 reads to profit, so 1 read(s) in practice.
```

**When the 1-hour tier wins.** A 2x write is worth it when your gaps between calls exceed 5 minutes. That is a human conversation with pauses, a batch job, or a nightly agent. It is not worth it for a tight tool-calling loop, where the 5-minute entry never expires anyway.

### Reading the usage object

```
usage.input_tokens                  ONLY the tokens after the last breakpoint
usage.cache_read_input_tokens       tokens served from the entry, at 0.1x
usage.cache_creation_input_tokens   tokens written into the entry, at 1.25x or 2x
usage.cache_creation.ephemeral_5m_input_tokens    the split, by TTL
usage.cache_creation.ephemeral_1h_input_tokens
```

The identity to hold on to:

```
total_input_tokens = cache_read_input_tokens + cache_creation_input_tokens + input_tokens
```

A team that reports `input_tokens` as "input tokens" on a dashboard will show a number near zero for a heavily cached agent and never question it. That exact bug is documented in a public issue against an observability product: an agent run whose true cost was $0.522 was reported as $0.238, which is 45.5% of actual, because the instrumentation emitted neither cache reads nor cache writes and logged the input as **20 tokens**. Twenty tokens for a multi-turn agent run is an obviously wrong number, and it sat on a dashboard unnoticed because it was presented with the same confidence as a correct one.

### Run the lab

```
python phase03_economics/cache_control_lab.py --explain          # no key needed
export ANTHROPIC_API_KEY=sk-ant-...
python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5
python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5 --no-cache
python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5 --break-it
```

Turn 1 costs **more** than the control run, because you paid the write premium. From turn 2 the per-turn cost drops hard. The script prints a running total so you can see the exact turn where the cached run overtakes the control.

`--break-it` puts a timestamp block **above** the breakpoint. Every turn then reports a cache creation and no read. You pay the premium repeatedly and collect the discount never. That is the single most expensive mistake in explicit caching, and it is the same mistake as Phase 0's Story 1 wearing different clothes.

### Two rules that are easy to miss

**The silent no-op.** A prefix below the model's minimum is not cached, and no error is returned. The minimums vary a lot: 512 tokens on some models and 4,096 on others. The price sheet now carries `min_cache_tokens` per model, and the lab warns you before it spends anything.

**Batch jobs want the long tier.** Provider guidance is explicit: because a batch can take longer than 5 minutes, use the 1-hour duration for shared context inside a batch. And one feature does not work there. Pre-warming a cache with a zero-token generation is not supported inside a batch, because the entry would expire before the follow-up request ran.

**The discounts stack.** Anthropic states that the batch discount and caching discounts combine. The equivalent claim for OpenAI is **not** documented on its batch page, so do not assume it. The check is one experiment: submit a batch with a repeated long prefix and read the cached-token count in the output file.

**The sentence to remember:** explicit caching is a purchase, not a setting, so compute the break-even in reads before you place a breakpoint.

**The trap:** a volatile block above the breakpoint turns every request into a cache write. You then pay 1.25x for input that would have cost 1x if you had never enabled caching at all.

**Try this now:** run `python phase03_economics/cache_control_lab.py --explain --break-it` and read the block order it prints. Then predict, before running anything live, what the `written` and `read` columns will show on turn 3.

---

## 🧪 Hands-on lab — part A

Setup: `cd ~/Desktop/project/code/study-material/inference-internals/code && pip install -e .`

**Live-run status, stated honestly:** every offline script was executed on the author's machine on 2026-09-12, and the outputs printed above are real outputs from those runs. No API key was available on this machine, so E4 to E8 were not executed against a live provider. Their command flags were checked against the shipped scripts.

- [ ] **E1 (offline).** Test the money arithmetic before you trust it.
  - Run: `python pricing.py --self-test`
  - Expected: eight checks pass, including "unknown cached price falls back to full price".
  - Then break it on purpose. Open `pricing.py`, change that fallback to `0.0`, and rerun. One check fails and tells you exactly which mistake you just made. Change it back.
  - Teaches: a cost module is a piece of software with a correctness property, not a one-line formula.

- [ ] **E2 (offline).** Read your own price sheet.
  - Run: `python pricing.py --role deep` then `python pricing.py --role cheap`
  - Expected: a `Price` row for each, and a `cached/input ratio` line.
  - Then edit `prices.yaml`. Replace both models with the ones you actually use, fill in every field you can find on the provider's pricing page, and set `priced_on` to today. Leave a field out rather than guessing it.
  - Teaches: the price sheet is the input to every number in this phase. A guessed price produces a confident wrong answer.

- [ ] **E3 (offline).** See the gap your Phase 1 meter was hiding.
  - Run: `python phase03_economics/cost_meter.py --replay --role deep`
  - Expected: the cold call shows a zero gap. The warm call shows the naive formula overstating by about 66%, and the warm call priced 2.96x cheaper than the cold one. The batch lines show a further halving.
  - Then run with `--role cheap` and compare the ratios. They differ, because the cached-to-input ratio differs per model.
  - Teaches: the size of the prize, before you spend anything measuring it live.

- [ ] **E4 (UNVERIFIED against a live provider).** See a real cache hit on your own account.
  - Run: `python phase03_economics/cost_meter.py --model <your-model> --role cache_demo`
  - Expected: call 1 reports 0 cached tokens. Call 2 reports most of the 12,000-token prefix as cached, and the gap column shows the naive formula overstating by more than half.
  - If call 2 also reports 0: read the diagnosis the script prints. The usual causes are a prefix under the minimum, too long a pause between calls, or a gateway that drops the details object.
  - Costs at most: about $0.05.
  - Teaches: the cached-token count is the only proof caching is working.

- [ ] **E5 (break-it, UNVERIFIED against a live provider).** Destroy the hit with one line.
  - Edit `cost_meter.py` and prepend the current timestamp to the prompt inside `build_prompt`, so it lands at position 0. Rerun E4.
  - Expected: call 2 now reports 0 cached tokens and the true cost equals the naive cost. You changed roughly 25 characters and lost the entire discount.
  - Then move the timestamp to the END of the prompt and rerun. The hit comes back.
  - Teaches: Phase 0's Story 1, reproduced on your own bill in two minutes. Remove your edit afterwards.

- [ ] **E6 (break-it, UNVERIFIED against a live provider).** Fall below the minimum and get no error.
  - Run: `python phase03_economics/cost_meter.py --model <your-model> --role cache_demo --prefix-tokens 400`
  - Expected: both calls succeed, both report 0 cached tokens, and nothing anywhere says why. A prefix below the documented minimum is a silent no-op.
  - Then raise it to 1,200 and watch the hit appear.
  - Teaches: absence of an error is not evidence that a feature is working.

- [ ] **E7 (UNVERIFIED against a live provider).** Explicit caching, and find the break-even turn.
  - Run offline first: `python phase03_economics/cache_control_lab.py --explain`. Read the block order and the usage fields it names.
  - Then: `python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5` and again with `--no-cache`.
  - Expected: the script prints the break-even in reads before it starts. Turn 1 of the cached run costs MORE than the control, because you paid the write premium. By turn 2 or 3 the cached run's running total drops below the control's. Write down which turn.
  - Costs at most: about $0.10 for both runs.
  - Teaches: explicit caching is a purchase with a payback period, not a switch.

- [ ] **E8 (break-it, UNVERIFIED against a live provider).** Pay the premium forever and never collect.
  - Run: `python phase03_economics/cache_control_lab.py --model <model-id> --role claude --turns 5 --break-it`
  - Expected: every turn shows a non-zero `written` column and a zero `read` column. You paid 1.25x input on every single turn. This run costs more than never enabling caching at all.
  - Teaches: a volatile block above the breakpoint inverts the whole feature. Compare this total against the `--no-cache` control from E7 and write down the difference.

---

## 🔍 Check it yourself — questions against the course code

This course has no anchor repository, so these target the code you now own. The last one works on any repository you have.

1. Open `pricing.py` and find the `cost` function. Locate the line that chooses `cached_rate`. Explain in one sentence why it falls back to `price.input_per_mtok` rather than to `0.0`, and name the specific wrong conclusion the zero version would produce on a dashboard.

2. Open `prices.yaml`. The `gpt-4.1-mini` and `gpt-4.1` rows have no `cached_input_per_mtok`. That is deliberate. Read the comment block at the top, then answer: what does `pricing.py` charge for a cached token on those two models, and is that error in the safe direction or the dangerous one?

3. Open `phase03_economics/cost_meter.py` and find `extract_usage`. It contains two separate code paths that never share a summation. Write down, from the code alone, which provider includes cached tokens inside its base input count and which reports them separately. Then find the line that makes a silent mismatch impossible.

4. In any repository you own that calls an LLM: find where the response usage is read. Answer three questions. Does it record a cached-token count? Does it record cost per request, or only tokens? Is there any code that would notice if the cached count went to zero tomorrow? Three honest "no" answers is the normal starting point, and it is exactly Phase 0's Story 1 waiting to happen.
---

## ✅ Checkpoint 3A — answer in your own words

1. Show the math. A model prices input at $2.00 per million tokens, cached input at $0.20, cache writes at $2.50, and output at $12.00. Your agent step sends 20,000 input tokens of which 18,000 hit the cache, and generates 400 output tokens. (a) Compute the true cost. (b) Compute what the Phase 1 two-price formula would report. (c) State the factor by which the old meter overstates this request. (d) Your finance team uses the old number to set customer pricing. Name the specific business error that creates.

2. A colleague says: "We turned on prompt caching and our costs did not move, so caching does not work for our workload." Give three separate, specific causes that produce exactly that observation. For each one, name the single number you would look at to confirm or eliminate it.

3. Show the math, then decide. A provider charges 2x input for a one-hour cache write, 1.25x for a five-minute write, and 0.1x for a read. (a) Derive the number of reads needed before the one-hour tier profits. (b) Your agent makes one call every 12 minutes for an hour. Which tier, and why? (c) Your agent makes one call every 20 seconds for two minutes, then stops. Which tier, and why is the answer different?

4. This is broken. Your cost dashboard reports $0.24 for an agent run the provider billed at $0.52. The dashboard shows 20 input tokens and 13,545 output tokens for a multi-turn run with a large system prompt. (a) Name the specific cause. (b) Explain why 20 input tokens should have been obviously wrong to any reader. (c) Name the two usage fields that were missing. (d) Say why this class of bug survives code review.

5. Walk me through what happens. Your agent serves a burst of 10 identical requests at once, at cold start, each carrying the same 12,000-token system prompt, on a provider that charges 1.25x for cache writes. (a) Trace what the cache does across those 10 requests. (b) Compare the total input cost against the same 10 requests with caching disabled. (c) State the one change to your call pattern that fixes it, and what it costs you in latency.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) Uncached input is 20,000 - 18,000 = 2,000 tokens. 2,000 x $2.00 / 1e6 = $0.004. Cached 18,000 x $0.20 / 1e6 = $0.0036. Output 400 x $12.00 / 1e6 = $0.0048. True total $0.0124. (b) Naive: 20,000 x $2.00 / 1e6 + $0.0048 = $0.04 + $0.0048 = $0.0448. (c) $0.0448 / $0.0124 = about 3.6x. (d) You price the product against a cost 3.6x your real cost. You lose deals you could have won, and you cannot explain your own margin when someone checks the invoice.

2. Three causes with their confirming numbers. First, the prefix is below the minimum, so nothing caches and no error appears. Check the cached-token count; it is exactly 0 on every call. Second, something volatile sits early in the prompt, so every request is cold. The cached count is also 0, so separate this from the first cause by raising the prefix length and seeing whether anything changes. Third, the saving is real and your meter cannot see it. Check whether your code reads the cached-token field at all; if it does not, your cost number cannot move by construction. A fourth acceptable answer: writes cost 1.25x, so a write-heavy workload with few reads genuinely does not save.

3. (a) (2.00 - 1.00) / (1.00 - 0.10) = 1.11, so two reads. (b) A 12-minute gap means a five-minute entry always expires before reuse, so that tier gives you a write every time and no reads. The one-hour tier gives one write and four reads within the hour, which clears the two-read break-even. Choose one hour. (c) Calls 20 seconds apart never let a five-minute entry expire, so the cheaper 1.25x write is already reused. The extra 0.75x for the longer tier buys nothing. Choose five minutes.

4. (a) The instrumentation did not emit cache-read or cache-write tokens, so cost was recomputed from partial counts. (b) On that provider `input_tokens` counts only tokens after the last cache breakpoint, so a multi-turn run with a large system prompt cannot have 20 real input tokens. The field was read as if it meant total input. (c) `cache_read_input_tokens` and `cache_creation_input_tokens`. (d) The wrong number is plausible, arrives through the same code path as correct numbers, and is displayed with identical confidence. Nothing errors. Only reconciliation against the provider's own cost report catches it.

5. (a) A cache entry becomes usable only after the first response begins. All 10 requests start before any entry exists, so all 10 write and none read. (b) With writes at 1.25x, the 10 requests cost 1.25 times what they would have cost with caching switched off entirely. Caching made this burst more expensive, not less. (c) Send one warm-up call, wait for it to start returning, then fan out the remaining 9 against a warm entry. It costs you the latency of one extra round trip at the start of the burst.

</details>

---

## References & Further Learning

Every URL below was fetched and checked on 2026-09-12. Where a page blocked automated fetching or a claim could not be confirmed, the entry says so. Prices and limits in this area change faster than anything else in the course, so treat every number as dated rather than permanent.

### Must-read before the lab

**OpenAI prompt caching guide** — https://developers.openai.com/api/docs/guides/prompt-caching
The primary source for section 3.2. The older `platform.openai.com` path now redirects here, so cite this one. Focus on the prompt-cache-options section and the invalidation list.
Verified numbers: a 1,024-token minimum, a 30-minute sliding reuse window on current models, cache reads at 0.1x the input rate, **cache writes at 1.25x**, and at most four cache writes per request. Caches are not shared across organisations or across regional processing boundaries.
The write price is the part most secondary material omits. Caching is no longer free to try.

**Anthropic prompt caching** — https://platform.claude.com/docs/en/build-with-claude/prompt-caching
The primary source for section 3.3, and the better document of the two because it describes the lookup algorithm rather than only the API. Focus on how breakpoints work, the minimum-length table, the invalidation table, and the one-hour duration section.
Verified: a write creates exactly one entry, a hash of the prefix ending at your marked block. The system walks backward up to 20 blocks looking for a match. At most 4 breakpoints, with a 400 error on the fifth. Prefixes build in the order tools, system, messages. Minimum cacheable length runs from 512 to 4,096 tokens depending on the model, and below the minimum **nothing caches and no error is returned**. Reads cost 0.1x, five-minute writes 1.25x, one-hour writes 2x. The page states the break-even directly: one read for the five-minute tier, two reads for the one-hour tier.

**Anthropic rate limits** — https://platform.claude.com/docs/en/api/rate-limits
Read one fact from this page. On most models, only uncached input tokens count toward the input tokens-per-minute limit. The page's worked example: a 2,000,000 token-per-minute limit with an 80% hit rate processes an effective 10,000,000 tokens per minute. If you are throughput limited rather than cost limited, caching is still the answer.

### Deep dives

**Prompt Caching 201** — https://developers.openai.com/cookbook/examples/prompt_caching_201
The cleanest latency evidence available. Cached requests run about 7% faster at the 1,024-token minimum and up to 67% faster to first token at 150,000 tokens and above. It also reports one coding customer's hit rate improving from 60% to 87% after adopting a cache key.
Honest note: the workload is described only as "coding" and no model is named for that improvement.

**How We Cut LLM Costs by 59% With Prompt Caching** — ProjectDiscovery, 10 April 2026.
https://projectdiscovery.io/blog/how-we-cut-llm-cost-with-prompt-caching
The best production write-up on this topic, because it states its measurement method: effective per-token rates derived from real spend, compared against what the same volume would have cost at the standard rate. Focus on the weekly hit-rate table.
Conditions: an autonomous security-testing platform, 20 to 40 LLM steps per task, system prompts over 20,000 tokens per agent. The hit rate moved from 7.6% to 73.7% in the week they shipped the prompt reordering, and later to 85%. Savings moved from 59% to 70%. Their sharpest number is a comparison of two tasks with nearly identical token volume, one at a 91.8% cache rate and one at 3.2%, with roughly 60x the cost.

**How prompt caching cut our production AI agent input costs by 77%** — Deriv, 23 July 2026.
https://derivai.substack.com/p/prompt-caching-production-ai-agent-costs
A second independent production measurement: an 85.8% hit rate producing a 77% reduction in input-token cost.
Honest note the author states themselves: the dollar figures are illustrative because production volume is confidential. Use the percentages, not the dollars.

**Google context caching** — https://ai.google.dev/gemini-api/docs/generate-content/caching
Read it for the contrast. Implicit caching there carries the phrase "no cost saving guarantee", explicit caching is documented as beta, and storage is billed **by the hour** rather than as a one-time write premium. That single difference changes the break-even arithmetic completely.

**Batch APIs** — https://developers.openai.com/api/docs/guides/batch and https://platform.claude.com/docs/en/build-with-claude/batch-processing
Both price batch at 50% of synchronous rates. Focus on the limits and the expiry behaviour, which differ: one returns and bills completed requests when a batch expires, the other does not bill expired requests. One of the two states explicitly that batch and caching discounts combine and recommends the one-hour cache tier inside batches. The other does not document the interaction at all, so do not assume it.

### Cost accounting and alerting

**OpenTelemetry GenAI semantic conventions** — https://github.com/open-telemetry/semantic-conventions-genai
The attribute registry lives at `docs/registry/attributes/gen-ai.md` in that repository. There is no released version, so cite a commit. The one checked here is dated 2026-09-10.
What to take from it: all 118 attributes are development stability, cached tokens are defined as `gen_ai.usage.cache_read.input_tokens` and `gen_ai.usage.cache_write.input_tokens`, reasoning tokens as `gen_ai.usage.reasoning.output_tokens`, and detailed attributes are always subsets of the totals rather than additions.
What is missing: there is **no cost attribute**, and no batch attribute. A cost convention exists only as open pull request 443, proposing `gen_ai.usage.cost.amount`, `.currency` and `.source`. Adopt those names now to migrate cheaply later.
The trap: the standard token metric carries only an input-or-output dimension. With caching on, you cannot compute spend from it. Use span attributes.

**Provider usage and cost APIs** — https://platform.claude.com/docs/en/manage-claude/usage-cost-api
Read it to learn what the provider cannot do for you. Cost reporting is daily-bucketed on both major providers. This one documents roughly five minutes of lag on token data and states that amounts come back as decimal strings in the lowest currency unit. The other documents no reporting lag that could be found.
The conclusion this forces: daily data cannot drive per-request alerting, so you meter locally and reconcile daily.

**Spend limits** — https://developers.openai.com/api/docs/guides/spend-limits and https://developers.cloudflare.com/ai-gateway/features/spend-limits/
The first documents alerts versus hard limits, the error codes returned, and states twice that "Enforcement is not instantaneous, so recorded spend can slightly exceed the configured amount". The second offers per-provider, per-model and per-metadata budgets with fixed or rolling windows, and can fall back to a cheaper model instead of returning an error. It also admits that "a burst of concurrent requests can briefly exceed the limit" and that cost tracking is best-effort estimation.
Read both for the same lesson: every provider-side control is enforced against stale spend.

**Budgets and rate limits in a gateway** — https://docs.litellm.ai/docs/proxy/users
The only documented pre-call budget mechanism found. It reserves the worst-case cost from `max_tokens` before the request, rejects if the reservation would breach, then settles to the actual cost. It also documents its own weak spots honestly: a cross-pod counter that can come back stale after a restart, a fail-closed mode that rejects with 503 rather than admitting an unverifiable request, and the fact that a batch submission cannot be priced at all because the request carries a file reference rather than prompts.

**Update on Security at METR** — 31 August 2026.
https://metr.org/blog/2026-08-31-security-update/
The closest thing to a primary incident account in this area. Roughly $600,000 of API credits consumed over about three weeks through an exposed internal application. The three stated reasons detection failed are the section's thesis: high token volume looked normal, the dashboard did not show the relevant signal, and no spend ceiling existed because the tokens were free.
Read it first, before the rest of section 3.5.

**Token Budgets: An Empirical Catalog of 63 LLM-Agent Budget-Overrun Incidents** — June 2026.
https://arxiv.org/abs/2606.04056
Screened 167 candidates and retained 63 across 21 frameworks, with an inter-rater agreement of 0.837 on inclusion. Its largest cause clusters are retry loops and missing cost observability. Its one-sentence conclusion is the one to quote: it found no case where a budget overrun was prevented before a user paid for it.
Honest note: a single-author preprint with no peer review, and the agreement on its mechanism clusters is much weaker at 0.44. Cite the aggregate counts, not individual entries.

**A cost dashboard that was wrong by more than half** — https://github.com/langfuse/langfuse/issues/13807
A fully instrumented, reproducible case. True cost $0.522, dashboard cost $0.238, which is 45.5% of actual, because the instrumentation emitted neither cache reads nor cache writes and reported the input as 20 tokens for a multi-turn agent run. Read it as the concrete form of section 3.3's warning about `input_tokens`.

### Not verified, stated so you do not repeat it

- Whether OpenAI batch requests hit the prompt cache is **not documented** on its batch page. The equivalent Anthropic claim is documented. The check is one experiment: submit a batch with a repeated long prefix and read the cached-token count in the output file.
- A widely circulated "$47,000 runaway bill" story traces only to secondary posts whose own figures contradict the headline framing. There is no first-party source. The same applies to most large dollar figures in this topic area.
- A frequently cited post claiming a major vendor treats a sub-90% cache hit rate as a serious incident could not be found on that vendor's site. Treat it as misattributed.

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
  pricing.py --self-test                     → the money arithmetic, offline
  pricing.py --role deep                     → read your own price sheet
  cost_meter.py --replay --role cache_demo   → the size of the prize, offline
  cost_meter.py --model X --role cache_demo  → a real cache hit, live
  cache_control_lab.py --explain             → the request shape, offline
  cache_control_lab.py --model X --role claude          → explicit caching
  cache_control_lab.py --model X --role claude --break-it → pay forever
```

Part B covers routing cascades, batch APIs, and the per-request cost alerting that catches a cache regression in ten requests instead of four months.

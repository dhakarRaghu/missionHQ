# Phase 0 — Frame the problem (what happens between your API call and the answer)

You call `client.chat.completions.create()` and tokens come back. Between those two events, a real machine does work. That machine has a tokenizer, a queue, and a GPU that runs two different kinds of work. It also has a cache. If the cache hits, you pay about 10% of the normal input price. If it misses, you pay full price.

This machine explains three common mysteries:
- Why is the same prompt sometimes 2x slower?
- Why did the bill jump this month?
- Why does the answer start fast on some calls and slow on others?

This course teaches that machine from the application side. You will not build an inference server. You will learn enough to predict its behavior, and to make it cheap.

Time: 30-45 minutes. No code in this phase. The goal is to build the map first. The next phases walk the territory.

## What we cover in Phase 0:

```
┌─────────────────────────────────────────────────────────────────────┐
│  0.1  The machine behind the API   — what actually runs per request │
│  0.2  The three numbers that rule you — TTFT, TPOT, $/Mtok          │
│  0.3  Why this is YOUR problem     — app-engineer failure stories   │
│  0.4  The course map               — what each phase makes you able │
│       to do                                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 0.1 — The machine behind the API (what actually runs per request)

Why this matters: you already treat Postgres as a machine. You think about indexes, query plans, and pages. Most engineers treat the LLM API as a black box. A black box cannot be optimized. That difference is where your money goes.

Here is the whole pipeline for one request, end to end:

```
┌────────────┐   HTTP    ┌───────────────┐  queue  ┌──────────────────────────┐
│ Your app   ├──────────►│ Provider edge  ├────────►│ Inference server          │
│ (client)   │           │ (auth, route)  │         │                          │
└────────────┘           └───────────────┘         │  1. tokenize prompt       │
      ▲                                            │  2. PREFILL: all input    │
      │                                            │     tokens in parallel    │
      │   SSE stream of tokens                     │     → builds KV cache     │
      └────────────────────────────────────────────┤  3. DECODE loop: ONE      │
                                                   │     token per step,       │
                                                   │     re-reading KV cache   │
                                                   │  4. sample next token     │
                                                   │  5. detokenize, stream    │
                                                   └──────────────────────────┘
```

Two words from the diagram need definitions now. **Prefill** is the step that processes your whole prompt. **Decode** is the loop that generates the answer, one token at a time. The whole course builds on two facts about them.

**Fact 1: prefill and decode are different kinds of work on the same GPU.** Prefill processes all input tokens at the same time, in parallel. The limit is the GPU's math speed. So prefill is fast per token. Decode generates one token per step. Each step must re-read a growing store in GPU memory. The limit is memory speed, not math speed. So decode is slow per token.

This one difference explains output pricing. Every provider prices output tokens higher than input tokens. The ratio is roughly 3x to 8x across providers. Example: the course's `prices.yaml` (OpenAI list, 2026-09-01) prices `gpt-4.1` at $2.00 per million input tokens and $8.00 per million output tokens. That is a 4x ratio. The exact number is a business choice. The direction comes from the hardware.

**Fact 2: the KV cache explains almost everything else.** During prefill, the server computes and stores intermediate results for every token. That store is called the KV cache (K and V stand for "key" and "value" vectors; Phase 1 explains them). The KV cache lives in GPU memory. It explains four things at once:

- Long prompts use a lot of GPU memory.
- Providers can sell "prompt caching" at about 90% off, because they can reuse this store.
- The GPU can only serve a limited number of requests at once, because memory runs out.
- An agent loop that re-sends the same 20k-token system prompt every step, in a way that breaks the cache, wastes money on every step.

**Verify your understanding:** do not read ahead. Why can the server process 10,000 input tokens in the time it takes to generate about 40 output tokens?

---

## 0.2 — The three numbers that rule you

Why this matters: "the model feels slow" is not something you can act on. These three numbers are.

```
┌───────────────┬────────────────────────────┬────────────────────────────────┐
│ Number        │ What it is                 │ What controls it               │
├───────────────┼────────────────────────────┼────────────────────────────────┤
│ TTFT          │ Time to first token        │ prefill length (your prompt!), │
│               │                            │ queue time, cache hits         │
│ TPOT          │ Time per output token      │ model size, batch load,        │
│               │ (decode speed)             │ memory bandwidth               │
│ $/Mtok e2e    │ Dollars per million tokens │ model choice, cache hit rate,  │
│               │ END TO END, in AND out     │ output length discipline       │
└───────────────┴────────────────────────────┴────────────────────────────────┘
```

TTFT means "time to first token". TPOT means "time per output token". The full latency formula is:

total latency = TTFT + (output_tokens × TPOT)

These are two different problems with two different fixes. A slow TTFT is a prompt-size problem or a caching problem. A slow token stream is a model-choice problem or a provider-load problem. If you only measure total latency, you cannot tell which problem you have.

Example with numbers. A request takes 11 seconds. Case A: TTFT is 9s and decode is 2s. Your prompt is too big, or the cache missed. Case B: TTFT is 0.5s and decode is 10.5s. The model is slow per token, or the answer is too long. Same total. Opposite fixes.

**The sentence to remember:** TTFT is about your prompt. TPOT is about their GPU. The bill is about both.

**In your codebase:** most agent stacks record `input_tokens`, `output_tokens`, and cost per run. Almost none record TTFT or TPOT. Check yours. Today, a 40-second agent step and a 4-second one probably look identical in your run log, except for wall time. Phase 1 fixes that.

---

## 0.3 — Why this is YOUR problem (three app-engineer failure stories)

These are the standard ways application teams get hurt. Each story maps to a phase of this course.

**Story 1: the invisible 5x bill.** A team ships an agent with an 18k-token system prompt (tools, instructions, examples). Every loop step re-sends it. The prompt has a timestamp near the top. The timestamp changes every request. So the provider's prefix cache never matches, and the team pays full input price on every step. Moving the timestamp to the end of the prompt would have cut input cost by about 90% on cached steps. Nobody noticed for four months. Reason: they tracked cost per month, not per request. (Phases 2-3 cover caching mechanics and prompt layout.)

**Story 2: the retry that made it worse.** p99 latency spikes (p99 means the slowest 1% of requests). The team adds short timeouts and retries. But the TTFT spike came from the provider's queue under load. Every retry re-enters the same queue, with a cold cache. So retries double the load and the cost, and help nothing. The fix was streaming plus a TTFT-based health signal, not retries. (Phase 5 covers operations.)

**Story 3: "just switch the model."** Cost pressure arrives. The team switches everything to a cheaper mini model, globally. One week later, support-quality complaints arrive. The team had no eval gate and no routing layer. So their only choices were "expensive everywhere" or "cheap everywhere". The real answer has two parts. First, a role-based registry with routing per role — `deep`/`default`/`cheap`, the shape the course's `prices.yaml` uses. Second, an eval suite that tests quality before a model change ships. (Phases 3 and 6.)

**The hard truth:** none of these are model problems. All three are application-engineering problems. They live on your side of the API.

**In your codebase:** open whatever agent project you own. For each story, ask: would my system detect this today? Story 1: is there per-request cost alerting? Story 2: is TTFT recorded anywhere? Story 3: is there an eval gate on model changes? Three honest "no"s is the normal starting point. The course exists to turn them into "yes".

---

## 0.4 — The course map

```
┌──────┬──────────────────────────────┬─────────────────────────────────────┐
│Phase │ Title                        │ After it, you can…                  │
├──────┼──────────────────────────────┼─────────────────────────────────────┤
│  1   │ Core mental model            │ measure TTFT/TPOT/cost yourself and │
│      │                              │ explain any latency number you see  │
│  2   │ Internals                    │ predict KV-cache memory, reason     │
│      │                              │ about batching and prefix caching   │
│  3   │ Economics and tuning         │ cut a real bill: caching, routing,  │
│      │                              │ batch APIs, with before/after math  │
│  4   │ Ecosystem                    │ run vLLM/SGLang on a rented GPU,    │
│      │                              │ judge quantization and spec-decode  │
│  5   │ Production operations        │ set TTFT SLOs, stream, fall back,   │
│      │                              │ observe inference like a database   │
│  6   │ Senior design                │ do the self-host math and defend an │
│      │                              │ architecture in a design review     │
└──────┴──────────────────────────────┴─────────────────────────────────────┘
```

Rules of engagement for this course:
- Every exercise prints its own tokens, dollars, and latency. "It looks right" is never a result.
- Everything anchors to the course's own exercise codebase, plus your agent repo where you have one. You build the instruments as you learn.
- Exercises read prices and model names from `code/prices.yaml`. Edit that one file to match your real price sheet. Then the material stays correct when providers change prices.

**Try this now:** `export OPENAI_API_KEY=sk-...`. Any OpenAI-compatible endpoint also works (a gateway, vLLM). Every lab script accepts `--base-url` and `--key-env`. That is the whole setup for Phase 1.

---

## ✅ Checkpoint 0 — answer in your own words

1. Your `deep` role (`gpt-4.1` in the course's `prices.yaml`) costs $2.00/Mtok in and $8.00/Mtok out. A colleague says: "output is only 4x input, and our prompts are 50x longer than our outputs, so output cost does not matter." When are they right? When does an agent loop make them very wrong?
2. A request takes 11 seconds total. Name the two measurements you need before you can decide whether to blame your prompt or the provider.
3. Story 1 above: explain in one sentence WHY a timestamp near the top of the prompt defeats prefix caching. Use only what 0.1 told you about how prefill builds the KV cache.
4. The course meter prices every run as `input_tokens × input_per_mtok + output_tokens × output_per_mtok` (see `ttft_meter.py`). Name one real billing behavior this formula cannot represent. Hint: it is the subject of Story 1.
5. Design instinct check: suppose your price sheet points a role at a floating `-latest` tag. The provider silently upgrades the model behind the tag. Which of the three numbers from 0.2 changes first? What in your current stack would notice? (Careful — check what would actually notice.)

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. They are right for a single call. With a 50:1 length ratio and a 4x price ratio, output is about 8% of the bill. They are wrong for an agent loop, for two reasons. First, the loop re-sends the growing history every step, so input volume multiplies with the step count. Second, caching can later cut input cost by 90%, but output never caches. Also, output drives latency. Always compute per workload. Never argue from the ratio alone.
2. TTFT and TPOT. Both need a streaming measurement. Total latency alone cannot separate a queue-or-prefill problem (your prompt) from a decode problem (their load).
3. Prefix caching reuses stored results only for a byte-identical prefix. A changing timestamp near the top makes each request differ early. So nothing after the timestamp can be reused.
4. Cached-input tokens are billed at about 0.1x the input price. The two-price formula has no cached count and no cached price. Other examples: batch-API discounts, reasoning-token classes.
5. TPOT changes first, and possibly quality. A new model decodes at a different speed. The trick part: nothing notices. Typical stacks log neither TTFT nor TPOT. Cost only shifts if the price sheet changes, and a silent model swap does not touch your yaml.

</details>

## References & Further Learning

This phase is a map, so read nothing yet. The full curated reference list starts in Phase 1. It has talks with timestamps, the PagedAttention paper with section guidance, and provider caching docs. Each reference there is paired with the exercise it supports.

## Cheatsheet

```
The machine:   tokenize → PREFILL (parallel, compute-bound, builds KV cache)
                        → DECODE (serial, memory-bound, one token/step)
The numbers:   TTFT  = queue + prefill        ← your prompt's fault
               TPOT  = decode step time       ← their GPU's fault
               total = TTFT + out_toks × TPOT
The bill:      $ = in_toks×in_price + out_toks×out_price   (naive)
               real bills add: cached-input price (~10% of in_price)
The rule:      measure per request, not per month
This course:   prices.yaml = prices+roles | ttft_meter.py = the instrument | TTFT in your stack: nowhere (yet)
```

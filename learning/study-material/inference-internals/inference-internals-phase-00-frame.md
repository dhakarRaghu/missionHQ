# Phase 0 — Frame the problem (what happens between your API call and the answer)

You call `client.chat.completions.create()` and tokens come back. A token is a piece of text, often part of a word. Between the call and the answer, a real machine does work. It has a tokenizer, a queue, a cache, and a GPU that does two different kinds of work. If the cache hits, you pay about 10% of the normal input price. If it misses, you pay full price.

This machine explains three common questions:
- Why is the same prompt sometimes 2x slower?
- Why did the bill jump this month?
- Why does the answer start fast on some calls and slow on others?

This course teaches that machine from the application side. You will not build an inference server. You will learn enough to predict its behavior, and to make it cheap.

Time: 30 to 45 minutes. This phase has no code. It gives you the map. The next phases teach each part in detail.

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

Why this matters: to make the LLM API cheaper or faster, you must know what runs inside it. You already think about Postgres as a machine, with indexes, query plans, and pages. Most engineers treat the LLM API as a closed box. They cannot optimize what they cannot see.

Here is the whole path of one request:

```
┌────────────┐   HTTP    ┌────────────────┐  queue  ┌───────────────────────────┐
│ Your app   ├──────────►│ Provider edge  ├────────►│ Inference server          │
│ client     │           │ auth, routing  │         │                           │
└────────────┘           └────────────────┘         │  1. tokenize prompt       │
      ▲                                             │  2. PREFILL: all input    │
      │                                             │     tokens in parallel,   │
      │   SSE stream of tokens                      │     builds the KV cache   │
      └─────────────────────────────────────────────┤  3. DECODE loop: ONE      │
                                                    │     token per step,       │
                                                    │     re-reads KV cache     │
                                                    │  4. sample next token     │
                                                    │  5. detokenize, stream    │
                                                    └───────────────────────────┘
```

SSE means server-sent events. It is one long HTTP response that delivers small chunks. **Prefill** is the step that processes your whole prompt. **Decode** is the loop that generates the answer, one token at a time. The whole course builds on two facts about them.

**Fact 1: prefill and decode are different kinds of work.** Both run on the same GPU. Prefill processes all input tokens at the same time. The GPU's math speed limits it. So prefill is fast per token. Decode generates one token per step. Each step re-reads a growing store in GPU memory. Memory speed limits it, not math speed. So decode is slow per token.

This difference explains output pricing. Every model in the course's `prices.yaml` prices output tokens 4x to 6x higher than input tokens. Mtok means one million tokens. Example: `prices.yaml` prices `gpt-4.1` at $2.00 per Mtok in and $8.00 per Mtok out. That is 4x. The source is the OpenAI list price, read on 2026-09-01. The exact ratio is a business choice. The direction comes from the hardware.

**Fact 2: the KV cache explains most of the rest.** During prefill, the server stores results for every token. That store is the KV cache. K and V stand for "key" and "value" vectors. Phase 1 explains them. The KV cache lives in GPU memory. It explains four things:

- Long prompts use a lot of GPU memory.
- Providers sell "prompt caching" at about 90% off, because they can reuse this store.
- A GPU serves a limited number of requests at once, because memory runs out.
- An agent loop can re-send the same 20k-token system prompt every step. If the prompt breaks the cache, every step pays full price.

**The sentence to remember:** prefill reads your prompt in parallel. Decode writes the answer one token at a time. The KV cache connects them.

**The trap:** you treat input and output tokens as the same kind of cost. Output tokens cost 4x more in `prices.yaml`, and each one takes a full decode step.

**Verify your understanding:** do not read ahead. In an example setup, the server processes 10,000 input tokens in the time it generates about 40 output tokens. Why is that possible?

---

## 0.2 — The three numbers that rule you

Why this matters: you cannot act on "the model feels slow". You can act on these three numbers.

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

These are two different problems with two different fixes. A slow TTFT is a prompt-size problem or a caching problem. A slow token stream is a model-choice problem or a provider-load problem. Total latency alone cannot tell you which problem you have.

Example with numbers. A request takes 11 seconds. Case A: TTFT is 9s and decode is 2s. Your prompt is too big, or the cache missed. Case B: TTFT is 0.5s and decode is 10.5s. The model is slow per token, or the answer is too long. The total is the same. The fixes are opposite.

**The sentence to remember:** TTFT is about your prompt. TPOT is about the provider's GPUs. The bill is about both.

**The trap:** you log only total latency. Then Case A and Case B above look the same, and you apply the wrong fix.

**In your codebase:** most agent stacks record `input_tokens`, `output_tokens`, and cost per run. Almost none record TTFT or TPOT. Check yours. A 40-second agent step and a 4-second step probably differ only in wall time in your run log. Phase 1 fixes that.

---

## 0.3 — Why this is YOUR problem (three app-engineer failure stories)

These are common ways application teams lose money or speed. Each story maps to a phase of this course.

**Story 1: the invisible 5x bill.** A team ships an agent with an 18k-token system prompt. It holds tools, instructions, and examples. Every loop step re-sends it. The prompt has a timestamp near the top, and the timestamp changes every request. A prefix cache reuses stored work only when the prompt start matches byte for byte. So the cache never matches, and the team pays full input price on every step. With the timestamp at the end, cached steps would cost about 90% less for input. Nobody noticed for four months, because the team tracked cost per month, not per request. Phases 2 and 3 cover caching and prompt layout.

**Story 2: the retry that made it worse.** p99 latency spikes. p99 means the slowest 1% of requests. The team adds short timeouts and retries. But the TTFT spike came from the provider's queue under load. Every retry enters the same queue again, with a cold cache. So retries double the load and the cost, and do not help. The fix was streaming plus a TTFT-based health signal. Phase 5 covers operations.

**Story 3: "just switch the model."** Costs are too high, so the team moves everything to a cheaper mini model. One week later, users complain about support quality. The team had no eval gate and no routing layer. An eval gate is a test suite that scores quality before a model change ships. Without these, the only choices were "expensive everywhere" or "cheap everywhere". The better answer has two parts:
1. A registry that maps each role to a model, such as `deep`, `default`, and `cheap`. The course's `prices.yaml` uses this shape.
2. An eval gate on every model change.

Phases 3 and 6 cover this.

**The sentence to remember:** none of these are model problems. All three are application problems on your side of the API.

**The trap:** you blame the provider first. In all three stories, the fix was in the team's own code or process.

**In your codebase:** open an agent project you own. For each story, ask: would my system detect this today? Story 1: is there per-request cost alerting? Story 2: is TTFT recorded anywhere? Story 3: is there an eval gate on model changes? Three honest "no" answers are the normal starting point. The course turns them into "yes".

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

Rules for this course:
- Every exercise prints its own tokens, dollars, and latency. "It looks right" is never a result.
- Every exercise uses the course's own code, plus your agent repo if you have one. You build the tools as you learn.
- Exercises read prices and model names from `code/prices.yaml`. Edit that one file to match your real price sheet. The material then stays correct when prices change.

**The sentence to remember:** each phase adds one skill, and every skill ends in a number you measure.

**The trap:** you skip Phase 1 and start at the phase with your current problem. Later phases use the Phase 1 terms and baselines without explaining them again.

**Try this now:** run `export OPENAI_API_KEY=sk-...`. Any OpenAI-compatible endpoint also works, such as a gateway or vLLM. Every lab script that calls an API accepts `--base-url` and `--key-env`. That is the whole setup for Phase 1.

---

## ✅ Checkpoint 0 — answer in your own words

1. Your `deep` role is `gpt-4.1` in `prices.yaml`. It costs $2.00/Mtok in and $8.00/Mtok out. A colleague says: "output is only 4x input. Our prompts are 50x longer than our outputs. So output cost does not matter." When are they right? When does an agent loop make them very wrong?
2. A request takes 11 seconds total. Name the two measurements you need before you blame your prompt or the provider.
3. Story 1: in one sentence, say WHY a timestamp near the top of the prompt stops prefix caching. Use only what 0.1 said about how prefill builds the KV cache.
4. The course meter prices every run as `input_tokens × input_per_mtok + output_tokens × output_per_mtok`. See `ttft_meter.py:420`. Name one real billing behavior this formula cannot represent. Hint: Story 1.
5. Suppose your price sheet points a role at a floating `-latest` tag. The provider silently upgrades the model behind the tag. Which of the three numbers from 0.2 changes first? What in your current stack would notice? Be careful here. Check what would really notice.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. They are right for a single call. Take 50 million input tokens for each million output tokens. Input costs 50 × $2 = $100. Output costs 1 × $8 = $8. Output is 8 / 108, about 7% of the bill. They are wrong for an agent loop, for two reasons. First, the loop re-sends the growing history every step, so input volume grows with the step count. Second, caching can later cut input cost by 90%, but output is never cached. Output also drives latency. Always compute per workload.
2. TTFT and TPOT. Both need a streaming measurement. Total latency alone cannot separate the two causes. A queue or prefill problem points at your prompt. A decode problem points at the provider's load.
3. Prefix caching reuses stored results only for a byte-identical prefix. A changing timestamp near the top makes each request differ early. So nothing after the timestamp can be reused.
4. Cached input tokens cost about 0.1x the input price. The two-price formula has no cached count and no cached price. Other examples: batch-API discounts and reasoning tokens.
5. TPOT changes first, and maybe quality. A new model decodes at a different speed. The hard part: nothing notices. Typical stacks log neither TTFT nor TPOT. Cost shifts only if the price sheet changes, and a silent model swap does not change your yaml.

</details>

## References & Further Learning

This phase is a map, so there is nothing to read yet. The full reference list starts in Phase 1. It has talks with timestamps, the PagedAttention paper with section guidance, and provider caching docs. Each reference there is paired with the exercise it supports.

## Cheatsheet

```
The machine:   tokenize → PREFILL (parallel, compute-bound, builds KV cache)
                        → DECODE (serial, memory-bound, one token/step)
The numbers:   TTFT  = queue + prefill        ← your prompt's fault
               TPOT  = decode step time       ← their GPU's fault
               total = TTFT + out_toks × TPOT
The bill:      $ = in_toks×in_price + out_toks×out_price   (naive)
               real bills add: cached-input price (~10% of in_price)
               output/input price in prices.yaml: 4x to 6x
The rule:      measure per request, not per month
This course:   prices.yaml = prices+roles | ttft_meter.py = the instrument | TTFT in your stack: nowhere (yet)
```

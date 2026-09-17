# Phase 1 — Core mental model (the request lifecycle)

Why this phase matters: after it, no latency number, price sheet, or caching discount will look random again. You will read "TTFT 2.1s, 34 tok/s, $0.004" and know three things. Which number is your fault. Which is the provider's. And which knob moves it. If you skip this phase, every later phase becomes a recipe you follow without understanding. That is exactly the failure mode this course exists to remove.

You will also build something real. A typical agent stack records tokens and cost per run. It does not know the TTFT of any run. By the end of the lab, you will have measured TTFT from the outside. In Phase 5, you will wire it into your own run telemetry.

Time: 4-6 hours including the lab. The exercises are not optional. The numbers YOU measure are the point.

## What we cover in Phase 1:

```
┌──────────────────────────────────────────────────────────────────────┐
│  1.1  Tokens            — the billing unit and its uneven economics  │
│  1.2  Prefill           — your prompt hits the GPU, TTFT is born     │
│  1.3  The KV cache      — the memory object that explains everything │
│  1.4  Decode            — one token per step, TPOT, the price gap    │
│  1.5  Sampling          — temperature, top_p, the determinism myth   │
│  1.6  Streaming & usage — measuring TTFT/TPOT/cost like an engineer  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1.1 — Tokens (the billing unit and its uneven exchange rate)

You know what a token is. Here is the part that costs you money: the tokenizer does not price all text equally. And your agent pays the difference again on every loop step.

Modern models use BPE tokenizers. BPE means "byte-pair encoding": the tokenizer has a fixed vocabulary of 100k-200k pieces, learned from training data. That data was mostly English and code. So common English words are one token each. Other text breaks into more, smaller pieces:

```
┌──────────────────────────┬──────────────┬──────────────────────────────┐
│ Content shape            │ ~chars/token │ Why                          │
├──────────────────────────┼──────────────┼──────────────────────────────┤
│ English prose            │ 4.0-4.5      │ vocabulary optimized for it  │
│ Python code              │ 3.0-3.5      │ good, but symbols fragment   │
│ Compact JSON             │ ~2.5-3.5     │ quotes/braces are tokens     │
│ Pretty-printed JSON      │ ~2.0-3.0    │ every indent costs tokens    │
│ Hindi / Devanagari       │ ~1.0-2.0    │ underrepresented in vocab    │
└──────────────────────────┴──────────────┴──────────────────────────────┘
   (Ratios are what matter — measure your own exact numbers in E1.)
```

Why an application engineer must care, in order of money:

1. **Agent history multiplies the cost.** Your agent loop re-sends the whole conversation on each step. Suppose a tool returns pretty-printed JSON on step 1. You do not pay its token count once. You pay it again on step 2, step 3, and every step after. Ten steps later, one verbose tool result has been billed ten times.
2. **Multilingual products pay a hidden multiplier.** The same support ticket in Hindi can cost 2-4x the tokens of its English translation. Example: if Verly-style support traffic is half Hindi, and you only measured English, your per-conversation cost model is wrong.
3. **Schema design is cost design.** Field names in your structured outputs are tokens. `"customer_sentiment_classification"` costs more than `"sentiment"`. Across millions of calls, that is a real, recurring price difference.

**The sentence to remember:** you are not billed for text. You are billed for tokens, and the exchange rate depends on what the text looks like.

**The trap:** counting tokens client-side with tiktoken and treating the count as truth. Providers use different tokenizers. Claude's counts differ from OpenAI's for the same text. Client-side counts are for estimates and budget planning. The server's `usage` object is the invoice. E3 makes you compare both.

**Try this now:**
```bash
python phase01_lifecycle/tokenize_cost.py --role deep
```
It prices real content shapes with the prices in `code/prices.yaml`. Edit that file to match your real price sheet.

---

## 1.2 — Prefill (your prompt meets the GPU; where TTFT comes from)

Now the request leaves your code. What happens next is the most misunderstood part of LLM latency.

The server processes your ENTIRE prompt in one parallel pass. That pass is called prefill. Every input token goes through every model layer at the same time. This is one huge matrix multiplication, and GPUs are built for it. Prefill is **compute-bound**: the limit is the GPU's math units. Its memory system keeps up fine.

```
 Timeline of one request (no caching, simplified):

 t=0ms      HTTP arrives, auth, route to a replica
 t=5ms      tokenize: text → [128k ids]           ← microseconds, never the issue
 t=10ms     queue: wait for scheduler slot        ← invisible, varies with load
 t=60ms     PREFILL starts: all N input tokens through all layers, in parallel
            ├── every layer computes K,V vectors for every token
            └── those K,V vectors are WRITTEN to GPU memory  ← the KV cache
 t=60+X ms  first output token sampled ────────── TTFT ends here
 then       DECODE: +1 token per step until stop/max_tokens
```

Three consequences. You will use all three constantly.

**TTFT grows with input length.** The X in the timeline grows roughly linearly with prompt tokens, until queue noise dominates. A 40k-token agent context has two costs. It costs 40k tokens times the input price. It also costs seconds of TTFT on every single step. So when your agent "feels slow to start responding", check prompt size before you blame the provider.

**The queue hides inside TTFT.** From the outside, queue time and prefill time are one number. This matters during incidents. If TTFT spikes and your prompt size did not change, the cause is provider-side congestion (the queue), not your prompt. But this diagnosis only works if you measured TTFT separately all along. Total latency cannot separate the two. E5 shows the spread.

**Prefill is why input tokens are the cheap ones.** The GPU handles thousands of input tokens per second in prefill. It generates only tens of output tokens per second in decode. Look at `prices.yaml`: `gpt-4.1` prices output at 4x input ($2.00 / $8.00, OpenAI list as of 2026-09-01). Across providers the ratio runs roughly 3x-8x. The exact number is a pricing decision. The direction comes from the prefill/decode difference. The spread is useful too: if two models solve your task equally well, pick the one with the smaller output multiple for output-heavy work.

**The sentence to remember:** TTFT = queue + prefill. Prefill is parallel and fast per token. But you pay it on the whole prompt, on every request, unless a cache says otherwise.

**The trap:** saying "the model is slow today" when the real change was your own prompt growing. Agent frameworks append history silently. TTFT that creeps up over a session is usually YOUR context growing, not their GPU getting slower.

**Try this now:**
```bash
python phase01_lifecycle/prefill_scaling.py --model gpt-4.1-mini
```
Watch TTFT grow as the script scales the prompt from 500 to 4k to 16k tokens. (Non-reasoning models only. The lab setup section explains why.)

---

## 1.3 — The KV cache (the memory object that explains everything)

This is the center of the whole course. Prompt caching discounts, batch-size limits, provider queueing, GQA, PagedAttention, the cost of long contexts — all of it comes back to this one object.

**First pass (mental model):** during prefill, each layer computed two vectors for every token. They are called K (key) and V (value). Decode needs those vectors again at every step, because each new token "attends" over all previous tokens — it reads their K and V to decide what comes next. Without a cache, every decode step would recompute K and V for the whole history. That is O(t²) work per step, and O(n³) for the full generation. The cache brings each step down to O(t). The price of that saving is GPU memory. So the server keeps all K,V vectors in GPU memory. That store is the KV cache. It lives for your request's duration. It grows with every token, input or output.

```
 GPU memory during your request:

┌──────────────────────────────────────────────────────────────┐
│  Model weights (shared by ALL requests)          e.g. 16 GB  │
├──────────────────────────────────────────────────────────────┤
│  KV cache — request A  (grows every token)  ██████░░         │
│  KV cache — request B                       ████░░░░         │
│  KV cache — request C                       ███████░         │
│  ... as many requests as KV memory allows — THE batch limit  │
├──────────────────────────────────────────────────────────────┤
│  Activations / scratch (small)                               │
└──────────────────────────────────────────────────────────────┘
```

**Second pass (the math — memorize the formula, not the numbers):**

```
KV bytes per token = 2 × layers × kv_heads × head_dim × bytes_per_value
                     ▲
                     └── the 2 is K and V

Llama-3-8B, fp16:  2 × 32 × 8 × 128 × 2 B  = 128 KB per token
   → 8k-token context  = 1 GB   of GPU memory, for ONE request
   → 128k-token context = 16 GB — the whole model's weight budget again
```

As code, because you will reuse it in capacity arguments for years:

```python
def kv_bytes_per_token(layers, kv_heads, head_dim, dtype_bytes=2):
    return 2 * layers * kv_heads * head_dim * dtype_bytes   # 2 = K and V

def max_concurrent(gpu_gb, weights_gb, ctx_tokens, per_tok, util=0.9):
    free = (gpu_gb * util - weights_gb) * 1024**3           # vLLM-style headroom
    return int(free // (per_tok * ctx_tokens))

assert kv_bytes_per_token(32, 8, 128) == 131_072            # llama-3-8b: 128 KB
```

Run `python phase01_lifecycle/kv_math.py`. It shows why one 80 GB H100 serving Llama-3-8B fits only about 64 concurrent requests at 8k context. Real servers reserve headroom — vLLM defaults to `gpu_memory_utilization=0.9` — so about 57 in practice. That fit number IS the provider's capacity. It IS why they queue you at peak time. It IS what batch APIs sell: leftover slots at off-peak time, hence the ~50% discount.

Notice `kv_heads: 8` while the model has 32 attention heads. That is GQA (grouped-query attention): four query heads share each KV head, so the cache shrinks 4x. Think about what that means. Model designers changed the attention architecture itself, only to shrink this cache. That is how much it dominates serving cost. (Character.AI went further: multi-query attention plus cross-layer sharing, for a 20x reduction. The reference at the end has the full story.)

**Third pass (the most useful consequence):** attention is causal. That means a token's K and V depend only on the tokens BEFORE it, never after. So if two requests share an identical prompt PREFIX, the K,V vectors for that prefix are identical too. The server can keep the prefix's KV blocks and skip prefill for them completely. That is prompt caching. It also explains the size of the discount (about 90% off cached input): the provider skips real work, not only billing.

But it only works on an EXACT prefix match. One changed byte at position 100 invalidates everything after position 100:

```
 request 1:  [SYSTEM PROMPT 18k toks][timestamp 14:02][history...]
 request 2:  [SYSTEM PROMPT 18k toks][timestamp 14:03][history...]
                                     ▲
                            divergence here → the 18k tokens BEFORE it hit
                            cache, everything AFTER re-prefills. Put the
                            timestamp first instead and you cache nothing.
```

**Three things to internalize:**
- KV memory sets concurrency, not compute. This is true for you AND for your provider.
- Every architecture trick you hear about (GQA, MQA, PagedAttention, RadixAttention, sliding windows) is an attack on this one object.
- Cache friendliness is a property of YOUR prompt layout: stable bytes first, changing bytes last. You will use this properly in Phases 2-3.

**The sentence to remember:** the KV cache is where your prompt physically lives on the GPU. The rent for that memory is what you really pay.

**The trap:** believing "we send the same system prompt every time, so we must get cache hits." Assembly order, injected timestamps, shuffled tool lists, or one dynamic first line silently break prefix identity. Do not assume. Measure — E6 catches this live.

**Verify your understanding:** why can the server NOT cache the KV of your prompt's LAST 100 tokens when the first 100 changed? (The answer is in the causality sentence above.)

---

## 1.4 — Decode (one token per step; TPOT and the price gap)

Prefill ends. The first token streams out. From here, the GPU does a different kind of work.

Decode generates exactly one token per step. Each step does this: run the newest token through all layers, read the ENTIRE KV cache, sample the next token, append its K,V to the cache, repeat. The math per step is small. But every step must read the whole KV cache plus the model weights from GPU memory. Decode is **memory-bandwidth-bound**: the compute units wait while bytes move.

```
 PREFILL                              DECODE (per step)
┌─────────────────────────┐          ┌─────────────────────────┐
│ 10,000 tokens in ONE    │          │ read weights (16 GB)     │
│ parallel pass           │          │ read KV cache (growing)  │
│ GPU compute: ~saturated │          │ compute: very small      │
│ ~thousands of tok/s     │          │ emit ONE token           │
└─────────────────────────┘          └─────────────────────────┘
        compute-bound                     bandwidth-bound
        input tokens: cheap               output tokens: expensive
```

This is the asymmetry from Phase 0, now fully explained:

- **TPOT (time per output token)** is set by memory bandwidth and by how many requests share the GPU. Under heavy batching, your tokens stream slower even though your request did not change. TPOT is genuinely the provider's number. You can pick a smaller model. You cannot prompt-engineer faster decode.
- **The output premium in `prices.yaml`** ($2.00 in / $8.00 out on `gpt-4.1`, 4x) is the market price of this prefill-vs-decode difference.
- **Output length is a latency tool AND a cost tool.** total = TTFT + out_tokens × TPOT. At 25ms TPOT, every 100 output tokens adds 2.5 seconds. So `max_tokens`, short-output instructions, and structured outputs (which remove filler prose) are latency features as much as cost features.

**The sentence to remember:** input tokens are processed in parallel. Output tokens are generated one by one. You buy them from two different machines that happen to share a GPU.

**Three things to internalize:**
- Output tokens are the expensive, slow ones — in dollars AND in seconds, for the same physical reason.
- TPOT is the number you cannot prompt-engineer. Model choice is your only big lever.
- Output-length discipline (max_tokens, short-output instructions, structured outputs) cuts cost and latency at the same time.

**The trap:** benchmarking two models with one prompt each and comparing total latency. Different answers have different lengths, so total-latency comparisons mean nothing. Compare TTFT and TPOT separately, at a controlled output length. E4 does it properly.

**The 2026 addition — reasoning tokens (output you pay for but may never see).** Reasoning models think before they answer. Examples: the gpt-5 family and o-series, and "thinking" models like kimi and deepseek-r. The thinking is a hidden chain of internal text, generated before the visible answer. Mechanically it is normal decode: one token per step, KV cache growing, TPOT physics. But it lands on your invoice as `completion_tokens` you may never see. OpenAI-style reasoning models keep the thinking invisible; `usage.completion_tokens_details.reasoning_tokens` is the only trace. Thinking models stream it as `reasoning_content` deltas. Three consequences you must design around:

- **`max_tokens` caps thinking + answer TOGETHER.** A small cap can spend the whole budget on thinking. Then you get an EMPTY answer, and you pay full price for it. The lab's meter warns exactly when this happens.
- **Cost per VISIBLE token is a multiple of the sticker price.** Example: the model burns 900 reasoning tokens to produce a 300-token answer. Your effective output price is 4x the price sheet. So effort and thinking-budget parameters are cost knobs, not quality trivia.
- **User-perceived TTFT includes the whole thinking phase.** The first VISIBLE token arrives only after thinking ends. That can take seconds to minutes. The meter has a separate `visible` column for this. On non-reasoning models, the two numbers are the same.

Rule of thumb: use non-reasoning models for tasks that do not need thinking. When you do use a reasoning model, log reasoning tokens as their own column. They are a third token class, not noise.

**Try this now:**
```bash
python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 3
```
Your first real TTFT/TPOT/cost measurements, priced from `prices.yaml`. Keep the output. You will compare providers and models against it for the rest of the course.

---

## 1.5 — Sampling (temperature, top_p, and the determinism myth)

Each decode step ends with a probability score for every token in the vocabulary. These raw scores are called logits. Sampling turns the scores into one chosen token. You control it with parameters you have used but probably never watched work:

```
 logits over vocab
        │
        ▼
 temperature T        divide logits by T before softmax
   T→0   sharpen → argmax ("greedy")        T>1  flatten → riskier picks
        │
        ▼
 top_p (nucleus)      keep the smallest set of tokens whose probability
                      mass ≥ p; renormalize; sample from that set
        │
        ▼
 one token — appended to KV cache, loop continues
```

Definitions for the diagram. Softmax turns logits into probabilities that sum to 1. Argmax picks the single highest-scoring token; that is called greedy sampling. Temperature reshapes the probabilities: low values favor the top token, high values spread the choices. Top_p keeps only the smallest set of top tokens whose combined probability reaches p, then samples inside that set.

Practical settings, based on use and not guesses: extraction, classification, and structured output want temperature 0-0.2, because you want the most likely answer. Drafting and brainstorming want 0.7-1.0. The combination `temperature=0.7, top_p=0.1` is effectively greedy with extra steps. Change one knob at a time.

**Now the myth, because it will break your tests:** `temperature=0` does NOT make outputs reproducible on production APIs. Here is the chain of reasoning. Greedy sampling deterministically picks the argmax — of logits that are not themselves deterministic. Your request runs in a batch with strangers' requests. The batch shape changes how GPU kernels execute, which changes the ORDER of floating-point additions. Float addition is not associative: (a+b)+c can differ from a+(b+c) in the last digits. So logits wobble around the 6th decimal place. Sometimes the top two tokens are close enough that the wobble flips the argmax. One flipped token early in the answer changes everything after it.

Two counterarguments you will hear. Both have answers:
- "But OpenAI has `seed`." The `seed` parameter plus `system_fingerprint` promises best-effort determinism only. The fingerprint changes when the backend deployment changes. And batch-shape effects still reorder float additions within one fingerprint. Useful for debugging. Not a guarantee you can build tests on.
- Mixture-of-experts (MoE) models add a second source. An MoE model routes each token to a subset of "expert" sub-networks. Under load, that routing can differ between runs. Then your tokens touch different weights entirely. Several models behind modern APIs are MoE.

One more provider difference: PARAMETER POLICIES. Anthropic models reject requests that set both `temperature` and `top_p`. Reasoning models (gpt-5 family, o-series) reject both knobs entirely. A gateway passes these policies through. It does not normalize them. So sampling config must live per-model, never as one global setting.

Consequences you must design around:
- CI tests that assert exact LLM output will flake. Assert structure and meaning instead: schema-valid, eval score, key facts present.
- "Reproducible runs" come from caching your own outputs. They never come from sampling settings.
- A/B comparisons need more than one run per variant, even at temperature 0.

**The sentence to remember:** temperature 0 removes the randomness you added. It does not remove the randomness of the machine.

**The trap:** setting temperature globally for an agent. The planner call and the JSON-extraction call in the same loop want different temperatures. Per-call sampling config is the correct granularity. Check what your own runner does in the anchor section.

**Try this now:**
```bash
python phase01_lifecycle/sampling_lab.py --model gpt-4.1-mini --determinism-runs 8
```

---

## 1.6 — Streaming and usage (how to measure like an engineer)

Everything in this phase becomes usable through three plumbing facts.

**Fact 1: streaming makes TTFT measurable — and makes slow answers feel fast.** With `stream=True`, the server sends tokens as decode produces them. The transport is SSE (server-sent events: a long-lived HTTP response that delivers small chunks). Your TTFT instrument is simple. Timestamp the request. Timestamp the first content chunk. Subtract. Then TPOT = (total − TTFT) / (output_tokens − 1). Streaming also helps the product: 400ms to the first word feels instant, even when the full answer takes 8 seconds. Note the gap in most systems: if your product streams app events but never model tokens, then no number in your system can separate a slow-prefill request from a slow-decode request.

**Fact 2: the server's `usage` object is the invoice. Read it from the last stream chunk.** Pass `stream_options={"include_usage": true}`. The final chunk then carries `prompt_tokens` and `completion_tokens`, measured by the server. That is what you are billed on. Client-side token counting is an estimate. `usage` is ground truth. Agent frameworks expose this as `result.usage()` (Pydantic AI) or similar. Check that your cost accounting reads the server's usage, not a client-side estimate. One more thing `usage` will carry once caching enters (Phase 3): cached-token counts. Your current cost formula ignores them.

**Fact 3: `finish_reason` says WHY decode stopped — and `"length"` is an incident, not an answer.** Every completion ends with a reason. `stop` means the model finished, or hit a stop sequence (a string you configured to end generation). `length` means `max_tokens` cut the answer off mid-stream. Now think about what `length` does to a structured-output call: the JSON is truncated, the parse fails, and a naive retry re-pays the entire prompt to fail the same way. Two design rules follow. First, size `max_tokens` per call site, from the schema's worst case, plus reasoning budget on thinking models (see 1.4). Never use one global constant. Second, log `finish_reason` on every call. A rising `length` rate is the earliest warning that your outputs are being silently cut. E11 makes you watch this failure live.

Here is the whole instrument. Wrong way first. Both bugs are ones real teams ship:

```python
# WRONG: non-streaming "latency measurement" + client-side "billing"
t0 = time.perf_counter()
r = client.chat.completions.create(model=m, messages=msgs)   # no stream
latency = time.perf_counter() - t0        # ONE number: TTFT+decode fused —
                                          # you cannot tell prompt problems
                                          # from provider problems
tokens = len(tiktoken.get_encoding("o200k_base").encode(text))  # estimate ≠
cost = tokens * price / 1e6               # invoice; wrong tokenizer for Claude,
                                          # ignores message framing (and later,
                                          # cached tokens). Your books drift
                                          # from the provider's bill.

# RIGHT: stream, split the timings, bill from server usage
t0 = time.perf_counter(); ttft = None
stream = client.chat.completions.create(
    model=m, messages=msgs, stream=True,
    stream_options={"include_usage": True})
for chunk in stream:
    if chunk.usage is not None:                      # final bookkeeping chunk
        usage = chunk.usage                          # ← the invoice
    elif chunk.choices and chunk.choices[0].delta.content:
        ttft = ttft or time.perf_counter() - t0      # first visible token
total = time.perf_counter() - t0
tpot = (total - ttft) / max(usage.completion_tokens - 1, 1)
cost = (usage.prompt_tokens * p_in + usage.completion_tokens * p_out) / 1e6
```

**The trap:** some gateways silently drop `stream_options.include_usage`. Then `usage` is `None` at the end of the stream. If your code treats missing usage as zero, every call through that gateway is booked as free. Fail loudly on missing usage. The lab's `ttft_meter.py` prints a warning and labels its cost a lower bound.

```
 what to log, per model call (the Phase 5 target schema):
┌────────────────────────────────────────────────────────────┐
│ model, ttft_ms, total_ms, tpot_ms,                         │
│ input_tokens, output_tokens, cached_input_tokens,          │
│ cost_usd, finish_reason                                    │
└────────────────────────────────────────────────────────────┘
 typical stack:    ✓ model  ✓ tokens  ✓ cost   ✗ ttft  ✗ tpot  ✗ cached
```

So you can judge your own E4 numbers, here are reference ranges for API models on short prompts (as of 2026-09 — these change; your own measurements always win):

```
┌───────────────────────────────┬──────────────┬───────────────────────┐
│ model class                   │ TTFT         │ TPOT                  │
├───────────────────────────────┼──────────────┼───────────────────────┤
│ small/cheap ("mini" class)    │ 200-500ms    │ 10-30ms               │
│ frontier non-reasoning        │ 300-800ms    │ 30-80ms               │
│ reasoning (to VISIBLE answer) │ 1s-minutes   │ same decode physics   │
│ self-hosted 8B on one H100    │ 50-200ms     │ 5-15ms (light load)   │
└───────────────────────────────┴──────────────┴───────────────────────┘
 Are you 5x outside these ranges? Suspect your measurement method or a
 queueing incident first, not the hardware.
```

**The sentence to remember:** stream to measure. Let the server's usage object write the invoice, not your tokenizer.

**In your codebase:** before doing the lab, find where your agent stack reads usage after a run completes (Pydantic AI: `result.usage()`; raw SDK: the response's `usage`). You are about to measure, from the outside, the two numbers that post-run code can never see.

---

## 🧪 Hands-on lab — the exercises that teach Phase 1

Setup once: `cd ~/Desktop/project/code/study-material/inference-internals/code && pip install -e .` (or `uv sync`). API exercises need a key: `export OPENAI_API_KEY=sk-...` (or any OpenAI-compatible endpoint via `--base-url ... --key-env YOUR_VAR`).

**Model reality check (smoke-tested 2026-09-01):** the commands below use `gpt-4.1-mini`, a cheap NON-reasoning model. That choice is deliberate. Two model families break measurement labs if you substitute them. First, THINKING models (kimi, deepseek-r). They stream `reasoning_content` tokens before any visible answer, and bill them as completion tokens. The lab's meter handles this: it reports TTFT at the first streamed token of any kind, reports a separate `visible` time for the first answer token, and warns when `max_tokens` runs out during reasoning (use `--max-tokens 300` or more with those models). Second, OpenAI's reasoning models (gpt-5 family, o-series). These are worse for labs: they do NOT stream their reasoning, and they reject `max_tokens` and sampling parameters outright. The meter falls back automatically and warns. Measure on a non-reasoning model first. Compare thinking models afterward, on purpose.

Context limits the lab relies on (as of 2026-09-01 — verify in provider docs when this changes):

```
┌──────────────────────┬─────────────┬───────────────────────────────┐
│ model                │ context     │ note                          │
├──────────────────────┼─────────────┼───────────────────────────────┤
│ gpt-4.1-mini (OpenAI)│ 1,047,576   │ default lab model: cheap,     │
│                      │             │ non-reasoning, implicit       │
│                      │             │ prefix caching (E6)           │
│ gpt-4.1 (OpenAI)     │ 1,047,576   │ the `deep` role in prices.yaml│
│ your own models      │ look it up  │ add rows as you adopt them    │
└──────────────────────┴─────────────┴───────────────────────────────┘
```

Every script prints its own tokens, dollars, and latency. Record them — later phases reuse your numbers. Total spend for the whole lab is well under $1. Each exercise lists its own worst case.

- [ ] **E1.** Price content shapes with YOUR prices.
  - Run: `python phase01_lifecycle/tokenize_cost.py --role default`
  - Expected: table of 5 samples; Devanagari has the worst chars/token; pretty JSON costs ≥1.3x compact JSON.
  - If it fails: the default `code/prices.yaml` is missing — restore it, or pass `--models-yaml`.
  - Teaches: tokens are an uneven exchange rate, and you can measure it.

- [ ] **E2.** Audit an agent repo for the token tax.
  - Run: `grep -rn "json.dumps" <your-agent-repo> --include="*.py" | grep -v __pycache__` — use any agent codebase you own. No repo at hand? Run it on an installed framework, for example your site-packages copy of `pydantic_ai`.
  - Expected: you can CLASSIFY every hit. A hit is only a problem when its output lands in a prompt. `json.dumps(result, indent=2)` in a tool-return or memory-write path is the tax: pretty-printing inflates tokens about 1.3-2x. The same call in a DB adapter, wire format, or outbound message costs nothing. Count your dirty hits.
  - Teaches: tokenizer economics is a code-review skill. The audit matters even when it comes back clean.

- [ ] **E3.** Client estimate vs server invoice.
  - Run: `python phase01_lifecycle/ttft_meter.py --model x --count-only` (no API call), then `python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 1` and compare the count against `in=`.
  - Expected: same prompt text, different numbers. The server adds message framing, and non-OpenAI models' tokenizers differ from tiktoken. Close, never equal.
  - Teaches: usage is the invoice; tiktoken is an estimate for budgeting only.

- [ ] **E4.** Establish your TTFT/TPOT baselines.
  - Run: `python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 5`. Then repeat with `--model gpt-4.1 --role deep` — or any second provider you have, via `--base-url` — for a two-model comparison.
  - Expected: different TPOT and different prices across models and providers. Save the medians in a file. This is your baseline for the whole course. Costs at most: ~$0.05.
  - Teaches: model choice moves TPOT and price; it moves TTFT far less.

- [ ] **E5.** Prove TTFT scales with prompt size.
  - Run: `python phase01_lifecycle/prefill_scaling.py --model gpt-4.1-mini`
  - Expected: TTFT climbs from hundreds of ms toward seconds as input goes 500 → 16k tokens. Costs at most: ~$0.05/run at cheap-model prices.
  - Teaches: TTFT is mostly your prompt.

- [ ] **E6 (break-it).** Break a warm cache with one changed character — OpenAI models only.
  - Precondition: implicit prefix caching is OpenAI-style behavior (automatic, ≥1024-token prefix, ~5-10 min lifetime, 128-token block granularity — verify in the docs, these change). Claude models (native API or through any gateway) do NOT cache implicitly. They need explicit `cache_control` breakpoints, which is Phase 3's lab. Run this exercise against an OpenAI non-reasoning model, for example gpt-4.1-mini with an OpenAI key.
  - Run: `python phase01_lifecycle/prefill_scaling.py --model gpt-4.1-mini --sizes 16000,16000` (same prompt twice), then once more with `--mutate-at start`, then `--mutate-at end`.
  - Expected: run 2 TTFT drops vs run 1 (warm cache). `--mutate-at start` jumps back to cold: one flipped character at byte ~10 invalidated everything after it. `--mutate-at end` stays near-warm: the prefix up to the mutation still hit.
  - If unclear: your prefix was below the caching minimum, or the cache lifetime expired between runs. Rerun back-to-back at 32k.
  - Teaches: prefix caching is an exact match from byte zero. WHERE a byte changes decides WHAT you pay.

- [ ] **E7 (break-it).** Overflow the context window on purpose.
  - Run: `python phase01_lifecycle/prefill_scaling.py --model gpt-4.1-mini --break-it --context-limit 1047576`
  - Expected: a fast 400 rejection, `invalid_request_error`, with a message naming the limit and your token count. The exact shape is in the script's docstring. Copy the real error into your notes: your agent's compaction trigger in Phase 2 must catch exactly this, and a blind retry would resend the same oversized prompt. Costs at most: $0 on rejection. Warning: if you pass a `--context-limit` LOWER than the model's real limit, the request fits, is not rejected, and you pay for a giant prefill. The script sends 2x the limit to keep the outcome clear.
  - Teaches: overflow fails fast, costs nothing, and cannot be retried as-is.

- [ ] **E8.** Watch sampling parameters work — and learn your provider's parameter policy.
  - Run: `python phase01_lifecycle/sampling_lab.py --model gpt-4.1-mini`
  - Expected: temp 0 → tight, plausible answer. Temp 1.2 → looser, sometimes worse. top_p 0.1 alone → near-greedy. The final both-knobs combo prints whichever lesson your provider teaches: acceptance (OpenAI-style policy — note it behaved near-greedy, top_p dominated) or a 400 rejection (Anthropic policy, exact error printed). Either way the script continues. Costs at most: ~$0.02.
  - Teaches: knob behavior, plus the fact that sampling policy differs per provider. Config must be per-model. A gateway does not normalize it.

- [ ] **E9 (break-it).** Test the determinism claim with data.
  - Run: `python phase01_lifecycle/sampling_lab.py --model gpt-4.1-mini --determinism-runs 10`
  - Expected: usually ≥2 distinct outputs at temperature 0. If all 10 are identical, raise `--determinism-runs` or `--max-tokens` until they split. Costs at most: ~$0.03.
  - Teaches: never build tests that assert exact LLM bytes.

- [ ] **E10.** The output-length latency lever.
  - Run: `ttft_meter.py --model gpt-4.1-mini --role cheap --max-tokens 40` vs `--max-tokens 400` (3 runs each).
  - Expected: TTFT stays about the same; total time scales roughly linearly with output tokens; your E4 TPOT predicts the difference within ~20%.
  - Teaches: total = TTFT + out×TPOT is a formula you can verify yourself, not trivia.

- [ ] **E11 (break-it).** Truncate a structured output and see the broken result.
  - Run: `printf 'Return ONLY a JSON object with keys name, city, bio (a 60-word biography) for a fictional user. No prose.' > /tmp/json_task.txt && python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 1 --max-tokens 25 --prompt-file /tmp/json_task.txt --show-output`
  - Expected: `finish=length`, a stderr warning, and printed output that is JSON cut off mid-string — `json.loads` on it would raise an error. Rerun with `--max-tokens 300`: `finish=stop`, complete JSON. Costs at most: ~$0.001.
  - If it fails: the model wrapped the JSON in prose despite the instruction. That is a different failure, and exactly why constrained decoding exists (Phase 2 teaches it).
  - Teaches: `finish_reason` is the difference between an answer and an incident. Budget `max_tokens` per schema, and log the reason on every call.
  - (Live-run status: command flags verified against the shipped script; not yet run against OpenAI from this machine — no API key was available on 2026-09-02.)

---

## 🏢 Codebase anchor — things to check in your repo

1. Open `code/prices.yaml`. The `deep` role (`gpt-4.1`) is priced $2.00 in / $8.00 out (4x). After 1.2 and 1.4, explain that premium in one sentence of physics. Then note which pricing dimension is MISSING from this file's schema entirely. Hint: E6; it arrives with Phase 3, and today the schema cannot even represent it. Bonus: swap in the models and prices you actually use now. Every later phase reuses this file.
2. Open `code/phase01_lifecycle/ttft_meter.py`. Find the cost computation in `main()`: raw token counts × two prices. When your provider starts returning cached-input tokens in `usage`, that formula silently OVERCHARGES your own accounting: it bills cached tokens at full price. Write the fix's signature now: what third count and third price does it need?
3. Open `code/phase01_lifecycle/ttft_meter.py`, function `one_run()`. Find where `first_any` and `first_visible` are captured. Reading `usage` after a run completes can never produce these numbers: TTFT exists only at stream time. Now find the exact place in YOUR agent stack where a streaming wrapper or an httpx event hook would have to live to see first-byte time. You implement that in Phase 5.
4. In your own agent repo: find where token usage is read after a run, and which numbers get persisted. Draft (on paper only) the schema change from section 1.6's target: which three columns are missing for latency triage, and why is `finish_reason` worth storing? (When Phase 5 pages you at 2am, "did it stop on max_tokens?" is the first question.)

---

## ✅ Checkpoint 1 — answer in your own words

1. A `deep`-role run (`gpt-4.1`) reports: total 21s, input 42,000 tokens, output 380 tokens. Use YOUR measured TPOT from E4. Estimate how the 21s splits between TTFT and decode. Which side would prompt caching attack, and roughly how much of the 21s is it worth?
2. A colleague benchmarks two models with one prompt each and declares one "3x faster" from total latency. List the two methodological errors. Sections 1.4 and 1.5 each contain one.
3. Your agent's step latency creeps from 3s to 11s over a 25-step session. Provider status is green. TPOT is stable in your logs. Diagnose: (a) the mechanism, (b) the one-line fix category, (c) which of the three numbers from Phase 0 was the tell.
4. Walk the machine: for a 10k-token prompt and a 200-token answer, narrate the request's life through tokenize → queue → prefill → KV cache → decode → sampling → stream. Name the stage where TTFT is decided and the stage where TPOT is decided, and say where the KV cache grows.
5. Design under constraints: Verly-style voice support needs the first audio within 800ms. The knowledge context is 30k tokens. Using this phase only (no caching yet), name two levers that could reach the budget and one lever that provably cannot help.
6. Show the math: at `gpt-4.1-mini` prices ($0.40/$1.60 per Mtok), a 10-step agent loop re-sends a growing history. It starts at 3k tokens and grows 1k per step, with 300 output tokens per step. What is the total cost? What fraction is input? Now explain why "output is only 4x input" understated the real bill.
7. This is broken: E9 gave a colleague 10 identical outputs out of 10, so they shipped a test asserting exact bytes. It passed for a week, then flaked. Explain in two sentences why the test was always wrong, and what to assert instead.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. At 40ms TPOT (use YOUR E4 number): decode ≈ 380 × 0.04 ≈ 15s. So TTFT ≈ 6s, which is almost all 42k-token prefill plus queue. Caching attacks only the TTFT side: with ~90% of the prefix cached, most of that ~6s and ~90% of input cost disappear. The 15s of decode cannot be cached.
2. Error one (1.4): total latency mixes in output length. Different answers have different lengths, so compare TTFT and TPOT separately at a controlled `max_tokens`. Error two (1.5): one run proves nothing. Sampling and batch noise vary between runs, so compare medians over several runs.
3. (a) The agent appends history every step, so prefill grows and TTFT creeps up. (b) Context management: compaction or pruning of history. (c) TTFT was the tell — it rose while TPOT stayed flat. Total latency alone could not have shown which side moved.
4. Key beats: tokenize (microseconds, never the issue) → queue (invisible, inside TTFT) → prefill builds KV for all 10k tokens in one parallel pass → first sampled token ends TTFT → 200 decode steps, each reading the whole KV cache and appending one token's K,V → sampling picks each token → chunks stream out. TTFT is decided in queue + prefill. TPOT is decided in decode. The KV cache grows during prefill AND by one token per decode step.
5. Two levers that help: (1) shrink the prompt — retrieve less of the 30k into context; (2) control output shape — stream, and produce a short first sentence with a tight `max_tokens`, so the first audio starts early. One lever that provably cannot help: sampling knobs (temperature, top_p). They act after the logits exist and move neither prefill nor decode speed.
6. Input across steps: 3k+4k+...+12k = 75k tokens → 75,000 × $0.40/M = $0.030. Output: 10 × 300 = 3k → 3,000 × $1.60/M = $0.0048. Total ≈ $0.035, and input is ≈ 86% of it. The 4x price ratio hides the volume effect: a loop multiplies input linearly with step count, because history is re-sent every step, while output stays flat. The volume asymmetry beats the price asymmetry.
7. Temperature 0 removes sampling randomness, not machine randomness: batch shape changes the float-addition order, logits wobble, and a near-tie argmax eventually flips. Ten identical runs were luck, not a guarantee. Assert structure and meaning (schema-valid, eval score, key facts present), never exact bytes.

</details>

---

## References & Further Learning

All links verified 2026-09-01. The order matters — it follows the phase.

**Must-read (paired with this phase):**
- 📄 [LLM Inference Performance Engineering: Best Practices](https://www.databricks.com/blog/llm-inference-performance-engineering-best-practices) — Databricks/MosaicML; the post that standardized TTFT/TPOT vocabulary. (30 min)
  - Focus: "Important Metrics for LLM Serving" and "Memory Bandwidth is Key". Skim the MPT-era benchmark numbers.
  - Read BEFORE the lab — it is the vocabulary E4/E10 assume.
- 📄 [Transformer Inference Arithmetic](https://kipp.ly/transformer-inference-arithmetic/) — kipply (Carol Chen, later Anthropic). The most-cited first-principles inference-math post; papers cite it. (60-90 min, dense)
  - Focus: "KV Cache", "Capacity", "Latency Calculations", "Batch Sizes". Skip "Model Parallelism" and the A100-era benchmark constants.
  - Read AFTER the lab, with `kv_math.py` open — redo its arithmetic with the script.
- 📄 [How continuous batching enables 23x throughput](https://www.anyscale.com/blog/continuous-batching-llm-inference) — Anyscale (Cade Daniel et al.); the standard batching explainer whose diagrams everyone reuses. (25 min)
  - Focus: static vs continuous batching sections; skip benchmarks and the Ray tail.
  - Read AFTER this phase, as the bridge into Phase 2.

**Deep dives (Phase 2 will assume these):**
- 📝 [PagedAttention / vLLM paper, SOSP 2023](https://arxiv.org/abs/2309.06180) — §2-3 now (decode loop, the 60-80% KV-waste measurement); §4 during Phase 2. Skip kernels (§4.4) and evals.
- 📝 [Orca, OSDI 2022](https://www.usenix.org/system/files/osdi22-yu.pdf) — invented continuous batching. §1-2 and §4.1-4.2 only ("selective batching" is the part summaries omit).
- 📄 [All About Transformer Inference — How To Scale Your Model, Part 7](https://jax-ml.github.io/scaling-book/inference/) — Google DeepMind, 2025; the modern successor to kipply with rooflines and worked problems. Do its Worked Problems after E10. TPU-flavored; the math transfers.

**War story (the payoff read):**
- 📄 [Optimizing AI Inference at Character.AI](https://blog.character.ai/optimizing-ai-inference-at-character-ai-2/) (+ [Part Deux](https://blog.character.ai/optimizing-ai-inference-at-character-ai-part-deux-2/)) — Noam Shazeer's team serving 20k QPS: 20x KV reduction, 95% inter-turn cache hit rate, int8, 33x cost cut. (15 min)
  - Read LAST in this phase. Every section 1.3 concept appears here with production numbers attached.

**Official docs to bookmark:**
- 📄 [Anthropic prompt caching docs](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching) — breakpoints, cache lifetimes and pricing (5-min cache: writes 1.25x, 1-hour cache: writes 2x; reads 0.1x), "what invalidates the cache". Skim now (it explains why E6 excludes Claude), work through it in Phase 3.
- 📄 [vLLM design doc: Automatic Prefix Caching](https://docs.vllm.ai/en/latest/design/prefix_caching/) — block hashing and eviction; what provider caching does under the hood. Read in Phase 2/4.

**Videos and talks (verified 2026-09-01; watch in this order):**
- 🎥 [The KV Cache: Memory Usage in Transformers](https://www.youtube.com/watch?v=80bIUggRJf4) — Bai Li, Efficient NLP (8:33). The 8-minute visual model of section 1.3.
  - Chapters: 1:15 self-attention review · 4:07 how the KV cache works · 5:55 memory usage example.
  - Watch FIRST, before or right after reading 1.3. Skip nothing — it is short.
- 🎥 [Deep Dive: Optimizing LLM Inference](https://www.youtube.com/watch?v=hMs8VNRy5Ys) — Julien Simon, ex-Hugging Face (36:11).
  - Watch 01:15-16:17 only for this phase: decoder-only inference (01:15), the KV cache (06:05), continuous batching (11:15). The speculative-decoding half (16:17+) belongs to Phase 4.
  - Watch AFTER the lab, as consolidation.
- 🎥 [Stanford CS336 Lecture 10: Inference](https://www.youtube.com/watch?v=EfM546A79aM) — Percy Liang & Tatsunori Hashimoto (1:25, Spring 2026 edition). The reference university lecture: prefill vs decode, arithmetic intensity, KV math, MQA/GQA, TTFT vs throughput.
  - Watch AFTER this phase, before Phase 2. Skip the alternative-architectures tail (SSMs, diffusion LMs).
- 🎥 [vLLM: Easy, Fast, and Cheap LLM Serving](https://www.youtube.com/watch?v=9ih0EmcXRHE) — Woosuk Kwon, PagedAttention's inventor, PyTorch Conf 2024 (23:32); pair with the [2025 update by Simon Mo](https://www.youtube.com/watch?v=Tv71-g75OgU) (24:47) for chunked prefill and the V1 engine. Park both until Phase 2/4.
- 🎥 [Efficient LLM Inference with SGLang](https://www.youtube.com/watch?v=Ny4xxErgFgQ) — Lianmin Zheng (xAI/SGLang, 24:36). The primary-source RadixAttention explanation; the mechanism behind E6's cache behavior. Park until Phase 2.
- 🎥 [Efficiently Serving LLMs](https://www.deeplearning.ai/courses/efficiently-serving-llms) — Travis Addair (Predibase), free DeepLearning.AI short course (~1h). The only resource here where you IMPLEMENT KV caching and continuous batching in notebooks. Optional hands-on companion to Phase 2; skip the multi-LoRA lessons.

---

## Cheatsheet

```
LIFECYCLE     tokenize → queue → PREFILL(parallel, compute-bound, builds KV)
              → DECODE(serial, bandwidth-bound) → sample → stream
LATENCY       TTFT  = queue + prefill        ← prompt size, cache, congestion
              TPOT  = per decode step        ← model size, provider load
              total = TTFT + out_toks × TPOT ← verify: E10
KV CACHE      bytes/token = 2 · layers · kv_heads · head_dim · dtype_bytes
              llama-3-8b fp16 ≈ 128 KB/tok → 1 GB @ 8k ctx  (kv_math.py)
              concurrency limit = free_HBM / (bytes_per_tok × ctx)
CACHING       exact PREFIX match from byte 0; stable content first,
              volatile (timestamps, user text) last; one early byte = full miss
PRICING       output ≈ 3-8x input across providers (prices.yaml: 4x)
              cached input ≈ 0.1x input (Phase 3; cost formula can't price it yet)
SAMPLING      extraction 0-0.2 | drafting 0.7-1.0 | one knob at a time
              temperature=0 ≠ reproducible (batch layout + fp order)
REASONING     hidden thinking = billed output; max_tokens caps think+answer
              (empty answer possible) · perceived TTFT = ttft + full thinking
STOP          finish_reason: stop=answer, length=TRUNCATED (parse incident);
              budget max_tokens per schema, log the reason every call (E11)
MEASURE       stream=True + stream_options.include_usage
              usage from final chunk = invoice; tiktoken = estimate
              log per call: ttft_ms, tpot_ms, in/out/cached toks, cost, finish_reason
THIS COURSE   prices.yaml=prices/roles · ttft_meter.py=TTFT/TPOT/cost meter
              cost formula has no cached price yet (Phase 3) · wire TTFT into
              your own telemetry in Phase 5
```

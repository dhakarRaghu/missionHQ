# Phase 1 — Core mental model (the request lifecycle)

Why this phase matters: after it, latency numbers, price sheets, and caching discounts stop looking random. You will read "TTFT 2.1s, 34 tok/s, $0.004" and know three things:

1. Which number your own code controls.
2. Which number the provider controls.
3. Which setting changes each number.

If you skip this phase, later phases become recipes you follow without understanding.

You will also build something real. A typical agent stack records tokens and cost per run. It does not know the TTFT of any run. By the end of the lab, you will have measured TTFT from the outside. In Phase 5, you will add it to your own run telemetry.

Time: 4 to 6 hours, including the lab. The exercises are not optional. The numbers YOU measure are the point.

## What we cover in Phase 1:

```
┌──────────────────────────────────────────────────────────────────────┐
│  1.1  Tokens            — the billing unit and its uneven economics  │
│  1.2  Prefill           — your prompt reaches the GPU, TTFT starts   │
│  1.3  The KV cache      — the memory object that explains everything │
│  1.4  Decode            — one token per step, TPOT, the price gap    │
│  1.5  Sampling          — temperature, top_p, the determinism myth   │
│  1.6  Streaming & usage — measuring TTFT/TPOT/cost like an engineer  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1.1 — Tokens (the billing unit and its uneven exchange rate)

The tokenizer does not price all text equally, and your agent pays the difference again on every loop step.

Modern models use BPE tokenizers. BPE means "byte-pair encoding". The tokenizer has a fixed vocabulary of pieces, learned from training data. OpenAI's `cl100k_base` has 100,277 pieces and `o200k_base` has 200,019. The counts come from tiktoken's `n_vocab`, run on 2026-09-17. Common English words are one token each. Other text splits into more, smaller pieces.

The course script measures this. Here is its output with `o200k_base`, run on 2026-09-17:

```
┌────────────────────────────┬───────┬────────┬───────────┬───────────────────────────────┐
│ Sample in tokenize_cost.py │ chars │ tokens │ chars/tok │ Why                           │
├────────────────────────────┼───────┼────────┼───────────┼───────────────────────────────┤
│ english prose              │  1056 │    201 │      5.25 │ vocabulary built for it       │
│ json compact               │   567 │    170 │      3.34 │ quotes and braces are tokens  │
│ python code                │  1062 │    348 │      3.05 │ symbols split into pieces     │
│ hindi prose                │   784 │    259 │      3.03 │ less common in the vocabulary │
│ json pretty                │   856 │    326 │      2.63 │ every indent costs tokens     │
└────────────────────────────┴───────┴────────┴───────────┴───────────────────────────────┘
   The five samples hold different text. Compare density, not totals.
   Measure your own content in E1.
```

An earlier draft gave English 4.0 to 4.5 characters per token and Hindi 1.0 to 2.0. The script output does not match those ranges, so the table now shows measured values.

Why an application engineer must care, in order of money:

1. **Agent history multiplies the cost.** Your agent loop re-sends the whole conversation on each step. Suppose a tool returns pretty-printed JSON on step 1. You pay its tokens on step 2, step 3, and every later step. After ten steps, you paid for that one tool result ten times.
2. **Multilingual products pay more per character.** The Hindi sample above needs 1.74x more tokens per character than the English sample. That is 259/784 against 201/1056. The script does not measure translation pairs. So the cost of one ticket in Hindi against its English translation is not checked here. Example: support traffic is half Hindi, and you measured only English. Then your per-conversation cost model is wrong.
3. **Schema design is cost design.** Field names in your structured outputs are tokens. `"customer_sentiment_classification"` costs more than `"sentiment"`. Across millions of calls, that difference repeats on every call.

Here is the cost of a formatting choice. The data is the same 12 rows that `tokenize_cost.py:52-59` uses. The token counts come from an `o200k_base` run on 2026-09-17:

```python
rows = [{"id": i, "status": "queued", "input_tokens": 1200 + i} for i in range(12)]

# WRONG: pretty-printed tool result. 326 tokens.
tool_result = json.dumps(rows, indent=2)

# RIGHT: compact separators. 170 tokens for the same data.
tool_result = json.dumps(rows, separators=(",", ":"))
```

The wrong version costs 1.92x the right one. Plain `json.dumps(rows)` gives 241 tokens, because it still adds a space after each comma and colon.

**The sentence to remember:** you are not billed for text. You are billed for tokens, and the exchange rate depends on what the text looks like.

**The trap:** you count tokens client-side with tiktoken and treat the count as the truth. Providers use different tokenizers. Claude's counts differ from OpenAI's for the same text. Use client-side counts for estimates and budget planning. The server's `usage` object is the invoice. E3 makes you compare both.

**Try this now:**
```bash
python phase01_lifecycle/tokenize_cost.py --role deep
```
It prices the samples with the prices in `code/prices.yaml`. With `--role deep`, it uses `gpt-4.1` at $2.00 per million input tokens. The last line says `pretty JSON costs 1.92x compact JSON for identical data.` Edit `prices.yaml` to match your real price sheet.

---

## 1.2 — Prefill (your prompt meets the GPU; where TTFT comes from)

Prefill is the first GPU step, and it sets most of your time to first token.

The server processes your ENTIRE prompt in one parallel pass. That pass is called prefill. Every input token goes through every model layer at the same time. This is one large matrix multiplication, and GPUs are built for it. Prefill is **compute-bound**. That means the GPU's math units limit its speed. Its memory keeps up.

```
 Timeline of one request (no caching, simplified, example times):

 t=0ms      HTTP arrives, auth, route to a replica
 t=5ms      tokenize: text → [128k ids]           ← microseconds, never the issue
 t=10ms     queue: wait for scheduler slot        ← invisible, varies with load
 t=60ms     PREFILL starts: all N input tokens through all layers, in parallel
            ├── every layer computes K,V vectors for every token
            └── those K,V vectors are WRITTEN to GPU memory  ← the KV cache
 t=60+X ms  first output token sampled ────────── TTFT ends here
 then       DECODE: +1 token per step until stop/max_tokens
```

This has three results. You will use all three often.

**TTFT grows with input length.** The X in the timeline grows about linearly with prompt tokens. At some point, queue noise is larger. A 40k-token agent context has two costs:
- 40k tokens times the input price.
- Seconds of TTFT on every step.

So when your agent is slow to start its answer, check the prompt size before you blame the provider.

**The queue is part of TTFT.** From the outside, queue time and prefill time are one number. This matters during incidents. Suppose TTFT spikes and your prompt size did not change. Then the cause is on the provider side: the queue. Your prompt did not cause it. This diagnosis works only if you already measure TTFT on its own. Total latency cannot separate the two. E5 shows the spread.

**Prefill is why input tokens are the cheap ones.** The GPU handles thousands of input tokens per second in prefill. It generates only tens of output tokens per second in decode. Look at `prices.yaml`. It prices `gpt-4.1` output at 4x input: $2.00 in and $8.00 out, from the OpenAI list on 2026-09-01. Across the five models in `prices.yaml`, the ratio is 4x to 6x. This course has not checked a wider range across providers. The exact number is a pricing decision. The direction comes from the prefill and decode difference.

The ratio also helps you choose. Suppose two models solve your task equally well. For output-heavy work, pick the one with the smaller output multiple.

**The sentence to remember:** TTFT = queue + prefill. Prefill is parallel and fast per token. But you pay for it on the whole prompt, on every request, unless a cache hits.

**The trap:** you say "the model is slow today" when your own prompt grew. Agent frameworks append history without telling you. If TTFT rises during a session, the usual cause is YOUR growing context. The provider's GPUs did not get slower.

**Try this now:**
```bash
python phase01_lifecycle/prefill_scaling.py --model gpt-4.1-mini
```
Watch TTFT grow as the script scales the prompt from 500 to 4k to 16k tokens. Use non-reasoning models only. The lab setup section explains why.

---

## 1.3 — The KV cache (the memory object that explains everything)

The KV cache is the GPU memory that holds your prompt during a request. Most of this course comes back to it. Caching discounts, batch-size limits, and provider queueing depend on it. So do GQA, PagedAttention, and the cost of long contexts.

**First pass, the mental model.** During prefill, each layer computes two vectors for every token. They are called K, for key, and V, for value. Decode needs those vectors again at every step. Each new token "attends" over all earlier tokens. That means it reads their K and V to decide what comes next.

Without a cache, every decode step would recompute K and V for the whole history. At step t, that is O(t²) work, and O(n³) for a full answer of n tokens. The cache brings each step down to O(t). The cost of that saving is GPU memory. The server keeps all K and V vectors in GPU memory. That store is the KV cache. It lives as long as your request. It grows with every token, input or output.

```
 GPU memory during your request (example sizes):

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

**Second pass, the math.** Learn the formula. You can always recompute the numbers.

```
KV bytes per token = 2 × layers × kv_heads × head_dim × bytes_per_value
                     ▲
                     └── the 2 is K and V

Llama-3-8B, fp16:  2 × 32 × 8 × 128 × 2 B  = 128 KB per token
   → 8k-token context   (8,192)   = 1 GB   of GPU memory, for ONE request
   → 128k-token context (131,072) = 16 GB, the size of the model weights again
```

Here is the same math in the course code. It is from `kv_math.py:41-44` and `kv_math.py:170-179`. Comments shortened, logic unchanged:

```python
def kv_bytes_per_token(layers: int, kv_heads: int, head_dim: int, dtype: str) -> int:
    # One K and one V vector per KV head, per layer.
    return 2 * kv_heads * head_dim * BYTES_PER_VALUE[dtype] * layers

# How many concurrent requests fit AFTER the model weights.
free = (args.gpu_gb - cfg["weights_gb"]) * 1024**3
if free < 0:
    return  # after printing "weights do not fit"
per_req = per_tok * args.context
fit = int(free // per_req) if per_req else 0
```

Run it:

```bash
python phase01_lifecycle/kv_math.py
```

Output on 2026-09-17, last lines:

```
--- llama-3-8b @ fp16 : 128 KB/token ---
  context   2,048 tokens → KV cache 256.0 MB
  context   8,192 tokens → KV cache 1.0 GB
  context  32,768 tokens → KV cache 4.0 GB
  context 131,072 tokens → KV cache 16.0 GB

On a 80 GB GPU: weights 16 GB, free 64.0 GB → fits 64 concurrent requests at 8,192 ctx.
```

So one 80 GB H100 that serves Llama-3-8B fits about 64 concurrent requests at 8k context. Real servers keep some memory back. vLLM's `gpu_memory_utilization` sets how much GPU memory vLLM may use. vLLM's engine-arguments page, fetched on 2026-09-17, gives the default as 0.92. The arithmetic: 80 × 0.92 = 73.6 GB. Take away 16 GB of weights, and 57.6 GB is left. At 1 GB per request, 57 requests fit.

An earlier draft used 0.9 with 57. With 0.9, the arithmetic gives 56. The script does not model this reserve.

That fit number is the provider's capacity. It is why they queue you at peak time. It is also what batch APIs sell: unused slots at off-peak times. `prices.yaml` sets `batch_multiplier: 0.50` for its models, which is a 50% discount.

Notice `kv_heads: 8` in the Llama-3-8B config, while the model has 32 attention heads. The Hugging Face `config.json` for Llama-3-8B shows `num_attention_heads: 32` and `num_key_value_heads: 8`. That is GQA, grouped-query attention. Four query heads share each KV head, so the cache is 4x smaller. Model designers changed the attention design itself, only to shrink this cache. That shows how much this cache drives serving cost. Character.AI went further. It used multi-query attention plus sharing across layers, and reports a KV cache "more than 20X" smaller. The reference list at the end has the details.

**Third pass, the most useful result.** Attention is causal. That means a token's K and V depend only on the tokens BEFORE it, never after. So if two requests share an identical prompt PREFIX, the K and V vectors for that prefix are identical too. The server can keep the prefix's KV blocks and skip prefill for them. That is prompt caching. It also explains the size of the discount, which is about 90% off cached input. The provider skips real work, not only a billing line.

But caching works only on an EXACT prefix match. One changed byte at position 100 invalidates everything after position 100:

```
 request 1:  [SYSTEM PROMPT 18k toks][timestamp 14:02][history...]
 request 2:  [SYSTEM PROMPT 18k toks][timestamp 14:03][history...]
                                     ▲
                            divergence here → the 18k tokens BEFORE it hit
                            cache, everything AFTER re-prefills. Put the
                            timestamp first instead and you cache nothing.
```

**Three things to remember from this section:**
- KV memory limits concurrency, not compute. This is true for you AND for your provider.
- GQA, MQA, PagedAttention, RadixAttention, and sliding windows all try to shrink or reuse this one object.
- Cache hits depend on YOUR prompt layout. Put stable bytes first and changing bytes last. Phases 2 and 3 use this in detail.

**The sentence to remember:** the KV cache is where your prompt lives on the GPU. You pay for that memory, whatever the price sheet calls it.

**The trap:** you believe that the same system prompt on every call means cache hits. Several things break prefix identity without any error. Examples are assembly order, injected timestamps, shuffled tool lists, and one dynamic first line. Do not assume. Measure it. E6 catches this live.

**Verify your understanding:** the first 100 tokens of your prompt changed. Why can the server NOT reuse the KV of the LAST 100 tokens? The causality sentence above has the answer.

---

## 1.4 — Decode (one token per step; TPOT and the price gap)

Decode generates the answer one token per step, and its speed is the TPOT you measure. It starts when prefill ends and the first token streams out.

Each decode step does five things:
1. Run the newest token through all layers.
2. Read the ENTIRE KV cache.
3. Sample the next token.
4. Append its K and V to the cache.
5. Repeat.

The math per step is small. But every step reads the whole KV cache plus the model weights from GPU memory. Decode is **memory-bandwidth-bound**. That means the compute units wait while bytes move.

```
 PREFILL, example sizes               DECODE, per step
┌─────────────────────────┐          ┌─────────────────────────┐
│ 10,000 tokens in ONE    │          │ read weights (16 GB)    │
│ parallel pass           │          │ read KV cache (growing) │
│ GPU compute: near full  │          │ compute: very small     │
│ thousands of tok/s      │          │ emit ONE token          │
└─────────────────────────┘          └─────────────────────────┘
        compute-bound                     bandwidth-bound
        input tokens: cheap               output tokens: expensive
```

This is the difference from Phase 0, now explained:

- **TPOT, time per output token,** depends on memory bandwidth and on how many requests share the GPU. Under heavy batching, your tokens stream slower even if your request did not change. TPOT is the provider's number. You can pick a smaller model. Prompt changes cannot make decode faster.
- **The output premium in `prices.yaml`** is the market price of this difference. For `gpt-4.1`, it is $2.00 in and $8.00 out, which is 4x.
- **Output length controls latency AND cost.** total = TTFT + out_tokens × TPOT. At 25 ms TPOT, every 100 output tokens add 2.5 seconds. So `max_tokens`, short-output instructions, and structured outputs are latency features as much as cost features. Structured outputs help because they remove extra prose.

**The sentence to remember:** the GPU processes input tokens in parallel and generates output tokens one by one. These are two different kinds of work on one GPU.

**Three things to remember from this section:**
- Output tokens are the expensive, slow ones. They cost more in dollars AND in seconds, for the same hardware reason.
- Prompt changes cannot improve TPOT. Model choice is your main control.
- Shorter outputs cut cost and latency at the same time. Use `max_tokens`, short-output instructions, and structured outputs.

**The trap:** you benchmark two models with one prompt each and compare total latency. Different answers have different lengths, so the totals are not comparable. Compare TTFT and TPOT separately, at a controlled output length. E4 does this correctly.

**The 2026 addition: reasoning tokens.** These are output tokens you pay for but may never see. Reasoning models think before they answer. Examples are the gpt-5 family and o-series, and "thinking" models such as kimi and deepseek-r. The thinking is a hidden chain of internal text, generated before the visible answer.

Inside, this is normal decode. It runs one token per step, the KV cache grows, and TPOT applies. But it appears on your invoice as `completion_tokens` you may never see. OpenAI-style reasoning models do not show the thinking. The only trace is `usage.completion_tokens_details.reasoning_tokens`. Thinking models stream it as `reasoning_content` deltas.

Three results you must design around:

- **`max_tokens` caps thinking and answer TOGETHER.** A small cap can spend the whole budget on thinking. Then you get an EMPTY answer, and you pay full price for it. The lab's meter warns when this happens. See `ttft_meter.py:127-129`.
- **Visible tokens cost more than the list price.** Example: a model uses 900 reasoning tokens for a 300-token answer. You pay for 1,200 tokens to get 300, so your real output price is 4x the price sheet. So effort and thinking-budget parameters are cost controls, not only quality settings.
- **User-perceived TTFT includes the whole thinking phase.** The first VISIBLE token arrives only after thinking ends. That can take seconds to minutes. The meter has a separate `visible` column for this. On non-reasoning models, the two numbers are the same.

Rule of thumb: use non-reasoning models for tasks that do not need thinking. When you use a reasoning model, log reasoning tokens in their own column. They are a third token class.

**Try this now:**
```bash
python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 3
```
These are your first real TTFT, TPOT, and cost measurements, priced from `prices.yaml`. Keep the output. You will compare providers and models against it for the rest of the course.

---

## 1.5 — Sampling (temperature, top_p, and the determinism myth)

Sampling picks one token from the model's scores at the end of each decode step. You control it with parameters you have used but probably never watched work.

Each decode step ends with a score for every token in the vocabulary. These raw scores are called logits. Sampling turns the scores into one chosen token:

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

Definitions for the diagram:
- **Softmax** turns logits into probabilities that sum to 1.
- **Argmax** picks the single highest-scoring token. Always picking the argmax is called greedy sampling.
- **Temperature** reshapes the probabilities. Low values favor the top token. High values spread the choices.
- **Top_p** keeps the smallest set of top tokens whose combined probability reaches p. It then samples inside that set.

Practical settings, by use:
- Extraction, classification, and structured output: temperature 0 to 0.2. You want the most likely answer.
- Drafting and brainstorming: temperature 0.7 to 1.0.
- `temperature=0.7, top_p=0.1` behaves almost like greedy sampling, because top_p=0.1 leaves very few tokens.
- Change one setting at a time.

**Now the myth, because it will break your tests.** `temperature=0` does NOT make outputs reproducible on production APIs. Here is the reasoning, step by step:

1. Greedy sampling always picks the argmax. But the logits themselves are not fixed.
2. Your request runs in a batch with other users' requests.
3. The batch shape changes how GPU kernels run. That changes the ORDER of floating-point additions.
4. Float addition is not associative. (a+b)+c can differ from a+(b+c) in the last digits.
5. So logits vary slightly, around the 6th decimal place.
6. Sometimes the top two tokens are close enough that this variation changes the argmax.
7. One changed token early in the answer changes everything after it.

Two counterarguments, with answers:
- "But OpenAI has `seed`." The `seed` parameter plus `system_fingerprint` promise best-effort determinism only. The fingerprint changes when the backend deployment changes. Batch-shape effects still reorder float additions under one fingerprint. `seed` helps with debugging. You cannot build tests on it.
- Mixture-of-experts (MoE) models add a second source. An MoE model sends each token to a subset of "expert" sub-networks. Under load, that routing can differ between runs. Then your tokens use different weights. Several models behind modern APIs are MoE.

Providers also differ in PARAMETER POLICIES:
- The course's `sampling_lab.py` docstring states that Claude models reject requests that set both `temperature` and `top_p`. This review did not confirm that on Anthropic's docs. E8 prints what your provider really does.
- Reasoning models, such as the gpt-5 family and o-series, reject both parameters.
- A gateway passes these policies through. It does not make them the same.

So sampling config must be set per model, never as one global setting.

Results you must design around:
- CI tests that assert exact LLM output will fail at random. Assert structure and meaning instead: valid schema, eval score, key facts present.
- Reproducible runs come from caching your own outputs. They never come from sampling settings.
- A/B comparisons need more than one run per variant, even at temperature 0.

**The sentence to remember:** temperature 0 removes the randomness you added. It does not remove the randomness of the machine.

**The trap:** you set temperature once for the whole agent. The planner call and the JSON-extraction call in the same loop need different temperatures. Set sampling config per call. Check what your own runner does, using the codebase anchor section.

**Try this now:**
```bash
python phase01_lifecycle/sampling_lab.py --model gpt-4.1-mini --determinism-runs 8
```

---

## 1.6 — Streaming and usage (how to measure like an engineer)

Streaming and the server's `usage` object are how you measure everything in this phase. Three facts make them work.

**Fact 1: streaming makes TTFT measurable.** With `stream=True`, the server sends each token when decode makes it. The transport is SSE, server-sent events. SSE is one long HTTP response that delivers small chunks.

Your TTFT instrument has four steps:
1. Record the time of the request.
2. Record the time of the first content chunk.
3. Subtract. The result is TTFT.
4. Compute TPOT = (total − TTFT) / (output_tokens − 1). `ttft_meter.py:134` does this.

Streaming also makes slow answers feel fast. The first word at 400 ms feels instant, even when the full answer takes 8 seconds. Check your own system for one gap. Suppose your product streams app events but never model tokens. Then no number in your system can separate a slow-prefill request from a slow-decode request.

**Fact 2: the server's `usage` object is the invoice. Read it from the last stream chunk.** Pass `stream_options={"include_usage": true}`. The final chunk then carries `prompt_tokens` and `completion_tokens`, counted by the server. The provider bills you on those numbers. Client-side token counting is an estimate. `usage` is the ground truth.

Agent frameworks expose this, for example as `result.usage()` in Pydantic AI. Check that your cost accounting reads the server's usage, not a client-side estimate. Once caching enters in Phase 3, `usage` also carries cached-token counts. Your current cost formula ignores them.

**Fact 3: `finish_reason` says WHY decode stopped. `"length"` is an incident, not an answer.** Every completion ends with a reason:
- `stop` means the model finished, or hit a stop sequence. A stop sequence is a string you configured to end generation.
- `length` means `max_tokens` cut the answer off.

Now think about what `length` does to a structured-output call. The JSON is cut off, and the parse fails. A simple retry pays for the whole prompt again and fails the same way. Two design rules follow:
1. Size `max_tokens` per call site, from the schema's worst case. On thinking models, add the reasoning budget. See 1.4. Never use one global constant.
2. Log `finish_reason` on every call. A rising `length` rate is the earliest sign that your outputs are being cut. E11 makes you watch this failure live.

Here is the whole instrument, wrong way first. Real teams ship both bugs. This snippet is simplified from `ttft_meter.py:65-137`, which also handles reasoning deltas and missing usage.

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
# E3 offline run, 2026-09-17: estimate = 44 tokens. Server count not measured.

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

**The trap:** some gateways drop `stream_options.include_usage` without an error. Then `usage` is `None` at the end of the stream. If your code treats missing usage as zero, every call through that gateway is booked as free. Fail loudly on missing usage. The lab's `ttft_meter.py:120-126` prints a warning and calls its cost a lower bound.

```
 what to log, per model call (the Phase 5 target schema):
┌────────────────────────────────────────────────────────────┐
│ model, ttft_ms, total_ms, tpot_ms,                         │
│ input_tokens, output_tokens, cached_input_tokens,          │
│ cost_usd, finish_reason                                    │
└────────────────────────────────────────────────────────────┘
 typical stack:    ✓ model  ✓ tokens  ✓ cost   ✗ ttft  ✗ tpot  ✗ cached
```

The table gives rough ranges for API models on short prompts, to judge your E4 numbers. This course did not measure them, because no API key was available. They date from 2026-09. Your own measurements win.

```
┌───────────────────────────────┬──────────────┬───────────────────────┐
│ model class                   │ TTFT         │ TPOT                  │
├───────────────────────────────┼──────────────┼───────────────────────┤
│ small/cheap ("mini" class)    │ 200-500ms    │ 10-30ms               │
│ frontier non-reasoning        │ 300-800ms    │ 30-80ms               │
│ reasoning (to VISIBLE answer) │ 1s-minutes   │ same decode mechanism │
│ self-hosted 8B on one H100    │ 50-200ms     │ 5-15ms (light load)   │
└───────────────────────────────┴──────────────┴───────────────────────┘
 Are you 5x outside these ranges? Suspect your measurement method or a
 queueing incident first, not the hardware.
```

**The sentence to remember:** stream to measure. Let the server's usage object write the invoice, not your tokenizer.

**In your codebase:** before the lab, find where your agent stack reads usage after a run ends. In Pydantic AI, it is `result.usage()`. In the raw SDK, it is the response's `usage`. Code that runs after the response cannot see TTFT or TPOT. You are about to measure those two numbers from the outside.

---

## 🧪 Hands-on lab — the exercises that teach Phase 1

Run status: the offline commands were run on 2026-09-17 on the author's machine. They are E1, the first half of E3, and the `kv_math.py` run in 1.3. Their Expected lines show that output. The API commands were not run on 2026-09-17, because no API key was available.

Setup once: `cd ~/Desktop/project/code/study-material/inference-internals/code && uv sync && source .venv/bin/activate`. In a plain virtual environment with pip, `pip install -e .` also works. API exercises need a key: `export OPENAI_API_KEY=sk-...`. Any OpenAI-compatible endpoint also works. Add `--base-url ... --key-env YOUR_VAR`.

**Model reality check.** An earlier version says these models were smoke-tested on 2026-09-01. This review could not re-run them. The commands below use `gpt-4.1-mini`, a cheap NON-reasoning model, on purpose. Two model families break measurement labs if you use them instead:

1. **Thinking models, such as kimi and deepseek-r.** They stream `reasoning_content` tokens before any visible answer. They bill them as completion tokens. The lab's meter handles this in three ways:
   - It reports TTFT at the first streamed token of any kind.
   - It reports a separate `visible` time for the first answer token.
   - It warns when `max_tokens` runs out during reasoning. Use `--max-tokens 300` or more with these models.
2. **OpenAI's reasoning models, the gpt-5 family and o-series.** These are worse for labs. They do NOT stream their reasoning. They reject `max_tokens` and sampling parameters. The meter falls back to `max_completion_tokens` and warns. See `ttft_meter.py:75-86`.

Measure on a non-reasoning model first. Compare thinking models later, on purpose.

Context limits the lab relies on, from `prices.yaml`, dated 2026-09-01. Check the provider docs when they change:

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

Every script prints its tokens, dollars, and latency. Record them for later phases. The whole lab should cost well under $1.

- [ ] **E1 (offline).** Price content shapes with YOUR prices.
  - Run: `python phase01_lifecycle/tokenize_cost.py --role default`
  - Expected: a table of 5 samples priced with `gpt-4.1-mini` at $0.4/Mtok input. Output on 2026-09-17: `json pretty` has the lowest chars per token, 2.63. `hindi prose` is 3.03 and `english prose` is 5.25. The last line says `pretty JSON costs 1.92x compact JSON for identical data.`
  - If it fails: `code/prices.yaml` is missing. Restore it, or pass `--models-yaml`.
  - Teaches: tokens are an uneven exchange rate, and you can measure it.

- [ ] **E2 (offline).** Audit an agent repo for the token cost of pretty JSON.
  - Run: `grep -rn "json.dumps" <your-agent-repo> --include="*.py" | grep -v __pycache__`. Use any agent codebase you own. If you have none, run it on an installed framework, such as your site-packages copy of `pydantic_ai`.
  - Expected: you can CLASSIFY every hit. A hit is a problem only when its output goes into a prompt. `json.dumps(result, indent=2)` in a tool-return or memory-write path is a problem. On the 1.1 sample, it cost 1.92x the compact form. In a DB adapter, wire format, or outbound message, it costs nothing.
  - Teaches: tokenizer cost is a code-review skill. The audit matters even when it finds nothing.

- [ ] **E3.** Client estimate against server invoice.
  - Run: `python phase01_lifecycle/ttft_meter.py --model x --count-only`. This makes no API call. Then run `python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 1` and compare the count with `in=`.
  - Expected, offline part, run on 2026-09-17: `client-side estimate (o200k_base): 44 tokens for the prompt text alone.` The live part should show a different `in=` number. The server adds message framing, and non-OpenAI tokenizers differ from tiktoken. The numbers are close, never equal.
  - Teaches: usage is the invoice. tiktoken is an estimate for budgeting only.

- [ ] **E4.** Record your TTFT and TPOT baselines.
  - Run: `python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 5`. Then repeat with `--model gpt-4.1 --role deep` for a two-model comparison. You can also use a second provider with `--base-url`.
  - Expected: different TPOT and different prices across models and providers. Save the medians in a file. This is your baseline for the whole course. Costs at most: ~$0.05.
  - Teaches: model choice changes TPOT and price. It changes TTFT much less.

- [ ] **E5.** Prove that TTFT grows with prompt size.
  - Run: `python phase01_lifecycle/prefill_scaling.py --model gpt-4.1-mini`
  - Expected: TTFT rises from hundreds of ms toward seconds as input grows from 500 to 16k tokens. Costs at most: ~$0.05 per run at cheap-model prices.
  - Teaches: TTFT depends mostly on your prompt.

- [ ] **E6 (break-it).** Break a warm cache with one changed character. OpenAI models only.
  - Precondition: implicit prefix caching is OpenAI-style behavior. It is automatic. OpenAI's prompt-caching guide, fetched on 2026-09-17, says three things:
    - The minimum cacheable prompt is 1,024 tokens for GPT-5.6 and later. For earlier models, the minimum depends on request settings.
    - Reported cached tokens round down to a multiple of 128.
    - Entries typically stay active for 5 to 10 minutes of inactivity.
  - Claude models do NOT cache implicitly, through the native API or any gateway. They need explicit `cache_control` breakpoints, which is Phase 3's lab. Run this exercise against an OpenAI non-reasoning model, such as gpt-4.1-mini with an OpenAI key.
  - Run, back to back:
    1. `python phase01_lifecycle/prefill_scaling.py --model gpt-4.1-mini --sizes 16000,16000`. This sends the same prompt twice.
    2. The step 1 command plus `--mutate-at start`.
    3. The step 1 command plus `--mutate-at end`.
  - Expected: in step 1, run 2 has a lower TTFT than run 1, because the cache is warm. In step 2, the first run is cold. The script changed one character at index 10 (`prefill_scaling.py:67`), so nothing after it matched. In step 3, the first run stays close to warm, because the prefix before the change still matched.
  - If unclear: your prefix was below the caching minimum, or the cache entry expired between runs. Rerun back to back with `--sizes 32000,32000`.
  - Teaches: prefix caching is an exact match from byte zero. WHERE a byte changes decides WHAT you pay.

- [ ] **E7 (break-it).** Overflow the context window on purpose.
  - Run: `python phase01_lifecycle/prefill_scaling.py --model gpt-4.1-mini --break-it --context-limit 1047576`
  - Expected: a fast 400 rejection, `invalid_request_error`, with a message that names the limit and your token count. The expected shape is in the script's docstring, `prefill_scaling.py:15-20`. Copy the real error into your notes. In Phase 2, your agent's compaction trigger must catch exactly this error. A blind retry would send the same oversized prompt again. Costs at most: $0 on rejection.
  - Warning: a `--context-limit` below the real limit makes the request fit. Then you pay for a huge prefill. The script sends 2x the limit so the result is clear (`prefill_scaling.py:330-332`).
  - Teaches: overflow fails fast, costs nothing, and cannot be retried unchanged.

- [ ] **E8.** Watch sampling parameters work, and learn your provider's parameter policy.
  - Run: `python phase01_lifecycle/sampling_lab.py --model gpt-4.1-mini`
  - Expected:
    - temperature 0 gives a focused, plausible answer.
    - temperature 1.2 gives a looser answer, sometimes worse.
    - top_p 0.1 alone behaves close to greedy.
    - The last combination sets both parameters. The script prints one of two results. OpenAI-style policy accepts it, and top_p dominates, so the answer is close to greedy. Anthropic-style policy rejects it with a 400, and the script prints the exact error. Either way, the script continues.
    - Without `--determinism-runs`, the script also runs 6 repeats at temperature 0 (`sampling_lab.py:202`).
  - Costs at most: ~$0.02.
  - Teaches: what each parameter does, and that sampling policy differs per provider. Config must be per model.

- [ ] **E9 (break-it).** Test the determinism claim with data.
  - Run: `python phase01_lifecycle/sampling_lab.py --model gpt-4.1-mini --determinism-runs 10`
  - Expected: usually 2 or more distinct outputs at temperature 0. If all 10 are identical, raise `--determinism-runs` or `--max-tokens` until they differ. Costs at most: ~$0.03.
  - Teaches: never build tests that assert exact LLM bytes.

- [ ] **E10.** Use output length to control latency.
  - Run: `python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 3 --max-tokens 40`, then the same command with `--max-tokens 400`.
  - Expected: TTFT stays about the same. Total time grows about linearly with output tokens. Your E4 TPOT should predict the difference within about 20%.
  - Teaches: total = TTFT + out × TPOT is a formula you can check yourself.

- [ ] **E11 (break-it).** Cut off a structured output and see the broken result.
  - Run: `printf 'Return ONLY a JSON object with keys name, city, bio (a 60-word biography) for a fictional user. No prose.' > /tmp/json_task.txt && python phase01_lifecycle/ttft_meter.py --model gpt-4.1-mini --role cheap --runs 1 --max-tokens 25 --prompt-file /tmp/json_task.txt --show-output`
  - Expected: `finish=length`, a stderr warning, and printed JSON that stops in the middle of a string. `json.loads` on it would raise an error. Rerun with `--max-tokens 300`. You should see `finish=stop` and complete JSON. Costs at most: ~$0.001.
  - If it fails: the model wrapped the JSON in prose, against the instruction. That is a different failure. It is the reason constrained decoding exists. Phase 2 teaches it.
  - Teaches: `finish_reason` tells an answer apart from an incident. Budget `max_tokens` per schema, and log the reason on every call.
  - Live-run status: command flags verified against the shipped script. Not yet run against OpenAI from this machine, because no API key was available on 2026-09-02. UNVERIFIED against OpenAI.

---

## 🏢 Codebase anchor — things to check in your repo

1. Open `code/prices.yaml`. The `deep` role is `gpt-4.1` (`prices.yaml:114`), priced at $2.00 in and $8.00 out, which is 4x. After 1.2 and 1.4, explain that premium in one sentence about the hardware. Then compare the `gpt-4.1` row (`prices.yaml:100`) with the `gpt-5.6-terra` row. Which pricing field does the `gpt-4.1` row lack? E6 is a hint. Read the file header to see why it is missing and what schema v1 could not represent. Bonus: add the models and prices you use now.
2. Open `code/phase01_lifecycle/ttft_meter.py`. Find the cost computation in `main()` at line 420. It multiplies raw token counts by two prices from `load_prices()` at line 53. Suppose your provider starts to return cached-input tokens in `usage`. Then this formula OVERCHARGES in your own accounting, because it bills cached tokens at full price. Write the signature of the fix now. What third count and third price does it need?
3. Open `code/phase01_lifecycle/ttft_meter.py`, function `one_run()` at line 65. Find where `first_any` and `first_visible` are set, at lines 88-89 and 113-118. Code that reads `usage` after a run cannot produce these numbers. To see first-byte time, your stack needs a streaming wrapper or an httpx event hook. Find where in YOUR agent stack it would go. You build that in Phase 5.
4. In your own agent repo, find where token usage is read after a run, and which numbers are stored. On paper only, draft the schema change from the 1.6 target. Which three columns are missing for latency triage? Why is `finish_reason` worth storing? In an incident in Phase 5, "did it stop on max_tokens?" is the first question.

---

## ✅ Checkpoint 1 — answer in your own words

1. A `deep`-role run (`gpt-4.1`) reports: total 21s, input 42,000 tokens, output 380 tokens. Use YOUR measured TPOT from E4. Estimate how the 21s splits between TTFT and decode. Which side would prompt caching reduce, and about how much of the 21s is it worth?
2. A colleague benchmarks two models with one prompt each. From total latency, they say one model is "3x faster". List the two method errors. Sections 1.4 and 1.5 each contain one.
3. Your agent's step latency rises from 3s to 11s over a 25-step session. The provider status page is green. TPOT is stable in your logs. Name (a) the mechanism and (b) the category of the one-line fix. Then name (c) the number from Phase 0 that showed the cause.
4. Walk through what happens for a 10k-token prompt and a 200-token answer. Follow the request through tokenize, queue, prefill, KV cache, decode, sampling, and stream. Name the stage that decides TTFT and the stage that decides TPOT. Say where the KV cache grows.
5. Design under constraints: a voice support product needs the first audio within 800 ms. The knowledge context is 30k tokens. Using this phase only, with no caching yet, name two changes that could meet the budget. Name one change that cannot help, and say why.
6. Show the math at `gpt-4.1-mini` prices: $0.40 in and $1.60 out per Mtok. A 10-step agent loop re-sends a growing history. It starts at 3k tokens and grows 1k per step, with 300 output tokens per step. What is the total cost? What fraction is input? Now explain why "output is only 4x input" understated the real bill.
7. This is broken: E9 gave a colleague 10 identical outputs out of 10. So they shipped a test that asserts exact bytes. It passed for a week, then failed. In two sentences, explain why the test was always wrong, and what to assert instead.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. Example with a 40 ms TPOT. Use YOUR E4 number. Decode ≈ 380 × 0.04 ≈ 15s. So TTFT ≈ 6s, which is almost all 42k-token prefill plus queue. Caching reduces only the TTFT side. With about 90% of the prefix cached, most of that 6s and about 90% of the input cost go away. The 15s of decode cannot be cached.
2. Error one, from 1.4: total latency includes output length. Different answers have different lengths. So compare TTFT and TPOT separately, at a controlled `max_tokens`. Error two, from 1.5: one run proves nothing. Sampling and batch noise vary between runs. So compare medians over several runs.
3. (a) The agent appends history every step, so prefill grows and TTFT rises. (b) Context management: compaction or pruning of history. (c) TTFT showed it. TTFT rose while TPOT stayed flat. Total latency alone could not show which side changed.
4. Tokenize takes microseconds and is never the issue. The queue is invisible and counts inside TTFT. Prefill builds KV for all 10k tokens in one parallel pass. The first sampled token ends TTFT. Then 200 decode steps follow. Each reads the whole KV cache and appends one token's K and V. Sampling picks each token, and chunks stream out. Queue plus prefill decide TTFT. Decode decides TPOT. The KV cache grows during prefill AND by one token per decode step.
5. Two changes that help: (1) shrink the prompt by putting less of the 30k tokens into context. (2) Control output shape. Stream, and ask for a short first sentence with a tight `max_tokens`, so the first audio starts early. One change that cannot help: sampling parameters such as temperature and top_p. They act after the logits exist, and change neither prefill speed nor decode speed.
6. Input across steps: 3k + 4k + ... + 12k = 75k tokens. 75,000 × $0.40/M = $0.030. Output: 10 × 300 = 3k tokens. 3,000 × $1.60/M = $0.0048. Total ≈ $0.035, and input is 0.030 / 0.0348 ≈ 86% of it. The 4x price ratio hides the volume effect. A loop grows input linearly with step count, because it re-sends history every step. Output per step stays flat. The volume difference outweighs the price difference.
7. Temperature 0 removes sampling randomness, not machine randomness. Batch shape changes the order of float additions, so the logits vary slightly. A near-tie argmax will change at some point. Ten identical runs were luck, not a guarantee. Assert structure and meaning: valid schema, eval score, key facts present. Never assert exact bytes.

</details>

---

## References & Further Learning

All links returned HTTP 200 on 2026-09-17. Two redirect, as noted. The order follows the phase.

**Must-read, paired with this phase:**

- **LLM Inference Performance Engineering: Best Practices, Databricks and MosaicML, 2023** — https://www.databricks.com/blog/llm-inference-performance-engineering-best-practices
  Focus on: "Important Metrics for LLM Serving" and "Memory Bandwidth is Key". Skim the MPT-era benchmarks. It set the common TTFT and TPOT terms, which E4 and E10 use. Read it BEFORE the lab. 30 minutes.
- **Transformer Inference Arithmetic, kipply (Carol Chen)** — https://kipp.ly/transformer-inference-arithmetic/
  Focus on: "KV Cache", "Capacity", "Latency Calculations", and "Batch Sizes". Skip "Model Parallelism" and the A100-era constants. Read it AFTER the lab, and redo its arithmetic with `kv_math.py`. 60 to 90 minutes. Redirects to `https://kipp.ly/p/transformer-inference-arithmetic`.
- **Achieve 23x LLM Inference Throughput & Reduce p50 Latency, Anyscale (Cade Daniel and others)** — https://www.anyscale.com/blog/continuous-batching-llm-inference
  Focus on: the static and continuous batching sections. Skip the benchmarks and the Ray section. Read it AFTER this phase, before Phase 2. 25 minutes.

**Deep dives, which Phase 2 assumes:**

- **Efficient Memory Management for Large Language Model Serving with PagedAttention, SOSP 2023** — https://arxiv.org/abs/2309.06180
  Focus on: sections 2 and 3 now, for the decode loop and the 60% to 80% KV-memory waste measurement. This review did not re-check that figure in the paper body. Read section 4 during Phase 2. Skip the kernels in section 4.4 and the evaluation.
- **Orca, OSDI 2022** — https://www.usenix.org/system/files/osdi22-yu.pdf
  Focus on: sections 1 and 2, and sections 4.1 and 4.2 only. This paper introduced continuous batching. Read the "selective batching" part closely.
- **All About Transformer Inference, How To Scale Your Model, Part 7, Google DeepMind, 2025** — https://jax-ml.github.io/scaling-book/inference/
  Focus on: the Worked Problems. Do them after E10. Its examples use TPUs, but the math is the same for GPUs.

**Production report:**

- **Optimizing AI Inference at Character.AI, Character.AI engineering blog, 2024** — https://blog.character.ai/optimizing-ai-inference-at-character-ai-2/
  Focus on: the KV cache section. Checked 2026-09-17, the post reports:
  - more than 20,000 inference queries per second
  - a KV cache more than 20X smaller, and a 95% cache rate
  - int8 quantization, and serving costs 33x lower than in late 2022

  Read it LAST in this phase. 15 minutes.
- **Optimizing AI Inference at Character.AI, Part Deux** — https://blog.character.ai/optimizing-ai-inference-at-character-ai-part-deux-2/
  Focus on: read it after the first part.

**Official docs to keep open:**

- **Anthropic prompt caching docs** — https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching
  Focus on: breakpoints, lifetimes, pricing, and what invalidates the cache. Fetched 2026-09-17: 5-minute writes cost 1.25x base input, 1-hour writes 2x, reads 0.1x, with per-model read exceptions. Skim it now to see why E6 excludes Claude. Study it in Phase 3. Redirects to `https://platform.claude.com/docs/en/build-with-claude/prompt-caching`.
- **vLLM design doc: Automatic Prefix Caching** — https://docs.vllm.ai/en/latest/design/prefix_caching/
  Focus on: block hashing and eviction. Read it in Phase 2 or Phase 4.

**Videos, in watch order. Titles checked on 2026-09-17. Durations and timestamps not re-checked:**

- **The KV Cache: Memory Usage in Transformers, Efficient NLP (Bai Li), 8:33** — https://www.youtube.com/watch?v=80bIUggRJf4
  Focus on: 1:15 self-attention review, 4:07 how the KV cache works, 5:55 memory usage example. Watch it FIRST, around your reading of 1.3.
- **Deep Dive: Optimizing LLM inference, Julien Simon, 36:11** — https://www.youtube.com/watch?v=hMs8VNRy5Ys
  Focus on: 01:15 to 16:17 only for this phase. That covers decoder-only inference at 01:15, the KV cache at 06:05, and continuous batching at 11:15. The rest belongs to Phase 4. Watch it AFTER the lab.
- **Stanford CS336 Language Modeling from Scratch, Spring 2026, Lecture 10: Inference, Percy Liang and Tatsunori Hashimoto, 1:25** — https://www.youtube.com/watch?v=EfM546A79aM
  Focus on: prefill against decode, arithmetic intensity, KV math, MQA and GQA, and TTFT against throughput. Skip the end part on SSMs and diffusion LMs. Watch it before Phase 2.
- **vLLM: Easy, Fast, and Cheap LLM Serving for Everyone, Woosuk Kwon and Xiaoxuan Liu, 23:32** — https://www.youtube.com/watch?v=9ih0EmcXRHE
  Focus on: PagedAttention, from its authors. Save it for Phase 2 or 4.
- **vLLM: Easy, Fast, and Cheap LLM Serving for Everyone, Simon Mo, PyTorch channel, 2025, 24:47** — https://www.youtube.com/watch?v=Tv71-g75OgU
  Focus on: chunked prefill and the V1 engine. Save it for Phase 2 or 4.
- **Efficient LLM Inference with SGLang, Lianmin Zheng, xAI, AMD Developer Central, 24:36** — https://www.youtube.com/watch?v=Ny4xxErgFgQ
  Focus on: RadixAttention, the mechanism behind E6's cache behavior. Save it for Phase 2.
- **Efficiently Serving LLMs, Travis Addair (Predibase), DeepLearning.AI short course, about 1 hour, free** — https://www.deeplearning.ai/courses/efficiently-serving-llms
  Focus on: the notebooks where you IMPLEMENT KV caching and continuous batching. Skip the multi-LoRA lessons. Optional, with Phase 2.

---

## Cheatsheet

```
LIFECYCLE     tokenize → queue → PREFILL(parallel, compute-bound, builds KV)
              → DECODE(serial, bandwidth-bound) → sample → stream
LATENCY       TTFT  = queue + prefill        ← prompt size, cache, congestion
              TPOT  = per decode step        ← model size, provider load
              total = TTFT + out_toks × TPOT ← verify: E10
TOKENS        o200k_base chars/token: english 5.25, hindi 3.03, pretty JSON 2.63
              pretty JSON = 1.92x compact JSON tokens (tokenize_cost.py)
KV CACHE      bytes/token = 2 · layers · kv_heads · head_dim · dtype_bytes
              llama-3-8b fp16 = 128 KB/tok → 1 GB @ 8k ctx  (kv_math.py)
              concurrency limit = free GPU memory / (bytes_per_tok × ctx)
              80 GB H100, 16 GB weights, 8k ctx: 64 fit; 57 at vLLM 0.92
CACHING       exact PREFIX match from byte 0; stable content first,
              volatile (timestamps, user text) last; one early byte = full miss
PRICING       output = 4-6x input across the 5 models in prices.yaml (gpt-4.1: 4x)
              cached input ≈ 0.1x input (Phase 3; Phase 1 cost formula can't price it)
              batch_multiplier in prices.yaml: 0.50
SAMPLING      extraction 0-0.2 | drafting 0.7-1.0 | one setting at a time
              temperature=0 ≠ reproducible (batch layout + fp order)
REASONING     hidden thinking = billed output; max_tokens caps think+answer
              (empty answer possible) · perceived TTFT = ttft + full thinking
STOP          finish_reason: stop=answer, length=TRUNCATED (parse incident);
              budget max_tokens per schema, log the reason every call (E11)
MEASURE       stream=True + stream_options.include_usage
              usage from final chunk = invoice; tiktoken = estimate
              TPOT = (total − TTFT) / (out_toks − 1)   (ttft_meter.py:134)
              log per call: ttft_ms, tpot_ms, in/out/cached toks, cost, finish_reason
THIS COURSE   prices.yaml=prices/roles · ttft_meter.py=TTFT/TPOT/cost meter
              ttft_meter cost formula has no cached price (Phase 3) · add TTFT
              to your own telemetry in Phase 5
```

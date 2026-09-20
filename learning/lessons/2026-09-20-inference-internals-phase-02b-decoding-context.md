# Inference Internals Phase 2B — Chunked Prefill, Constrained Decoding and Context Budgets

_Inference Internals, phase 2B. Assumes Phase 1 (the request lifecycle: tokens, prefill vs decode, KV cache, TTFT/TPOT, finish_reason) and Phase 2A (the scheduler loop, the token budget, the paged KV cache, radix-tree prefix caching). Three commands need no API key and no GPU; the live structured-output runs need one. There is a lab._

## Why you are here: the freeze, the schema and the 400

Your chat demo has median TTFT of 600ms and median total time of 4.2s. The dashboard is green. Users still report that the text "stops for a second" in the middle of an answer. Nothing you record shows it. In another service, you turn on strict JSON mode so a support-ticket pipeline stops crashing its parser, and a week later classification accuracy is down 9 points with valid JSON on every call. In a third, a long agent run dies at 3am with HTTP 400, and the retry loop resends the same oversized prompt three times. Production rejected it three more times, correctly, for the same reason.

Three failures, three different endpoints, one shared cause: something the server does with your tokens that you cannot see from the client. This phase is the client side of Phase 2. Part A showed how the server shares one GPU between many requests: the scheduler loop, the token budget and the paged KV cache. Part B covers the three problems you actually observe. A stream freezes mid-sentence. A strict schema changes answer quality. A long run fails with a 400.

Each of the three sections in this phase answers one of those failures. None of the three fixes is "get a better provider". All three are things you control from your own code today.

## What this phase teaches, and what it does not

Part A is a prerequisite. Section 2.4 builds on the scheduler loop and the token budget from section 2.1. Section 2.6 orders the prompt zones with the prefix rule from section 2.3: stable content first, because the radix-tree prefix cache in section 2.3 only rewards a stable prefix. This part does not explain those ideas again.

This part pays two debts from Phase 1:

- Phase 1 exercise E7 overflowed the context window on purpose and got a 400 back. Section 2.6 builds the compaction trigger that prevents it.
- Phase 1 exercise E11 truncated a JSON answer and said that constrained decoding exists. Section 2.5 teaches constrained decoding and measures its cost.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  2.4  Chunked prefill            the trade between TTFT and TPOT,        │
│                                  and the stream freeze                   │
│  2.5  Constrained decoding       token masking, and the constraint tax   │
│  2.6  Context budget and         the trigger that prevents Phase 1 E7,   │
│       compaction                 and the backstop that catches it        │
└──────────────────────────────────────────────────────────────────────────┘
```

Two things are named here and taught later. Prompt caching and its billing rules are Phase 3A, so when section 2.6 notes that compaction breaks cached prefixes, that is a pointer, not a lesson. Backend selection for self-hosted structured output is Phase 4A section 4.2, so section 2.5 tells you what the engine's fallback means without teaching how to configure the server.

Time: 1.5 to 2 hours. Three commands in this part need no API key and no GPU: `batching_sim.py`, `structured_lab.py --self-test`, and `compactor.py --simulate`. The live `structured_lab.py` runs need `export OPENAI_API_KEY=sk-...`. You can also use any OpenAI-compatible endpoint through `--base-url` and `--key-env`. Setup: use the same `code` directory and install step as part A.

## 2.4 Why does one long prompt freeze every stream in the batch?

Why this matters: section 2.1 of part A left one number without an explanation. Continuous batching produced a 764ms worst gap between two tokens of one answer. Your user sees that gap as a frozen stream. This section explains the cause and the fix.

Go back to the scheduler loop. One iteration runs one forward pass. That pass can do prefill work, decode work, or both. Now a new request arrives with a 24,000-token prompt. Without chunking, the server has two bad choices:

1. Run the whole 24,000-token prefill in one iteration. Every decoding request in the batch gets no token during that iteration.
2. Wait until the running decodes finish. The new request then gets a very long TTFT.

```
NO CHUNKING — one large prefill stops every stream in the batch (example)

  iteration:      1      2      3           4           5      6
  prefill  :      -      -      -    [24,000 tokens]    -      -
  decode   :   A B C  A B C  A B C        none       A B C  A B C
  duration :    18ms   18ms   18ms        720ms       18ms   18ms
                                       ▲
                          A, B and C all freeze for 720ms here
```

Chunked prefill splits that prompt. Each iteration takes one slice of the prefill plus all the decodes. Both share one token budget. In vLLM that budget is `max_num_batched_tokens`.

```
CHUNKED PREFILL — the same work, spread across iterations (example)

  iteration:    1        2        3        4        5        6
  prefill  :    -     2,045    2,045    2,045    2,045    2,045   ... (12 total)
  decode   : A B C    A B C    A B C    A B C    A B C    A B C
  duration : 18ms      80ms     80ms     80ms     80ms     80ms
                       ▲
         the new request's TTFT gets a little worse, and no stream freezes
```

**The sentence to remember:** prefill and decode share the same forward pass. A long prompt either waits or freezes the other streams. Chunking decides which.

The durations come from the simulator's cost model. Part A section 2.1 shows it at `batching_sim.py:49`. Three decodes cost 18 + 0.12 × 3 = 18.4ms. A 24,000-token prefill costs 24,000 × 0.03 = 720ms. A 2,045-token slice plus three decodes costs 61.4 + 18.4 = 79.8ms. The prompt needs 24,000 / 2,045 = 11.7 slices, so 12 iterations.

The budget is shared. With `max_num_batched_tokens=2048` and 3 decoding requests, the iteration spends 3 tokens on decode. It spends up to 2,045 on prefill. The simulator reserves the decode tokens first. `batching_sim.py:122` computes `room = max(token_budget - len(decoding) - prefill_tokens, 0)`. Without chunking, `batching_sim.py:128` sets `decoding = []`, so no decode runs in that pass. This order is not a quirk of the course code. Algorithm 3 of the Sarathi-Serve paper fills the budget the same way. Running decodes first, then partial prefills, then new requests. The paper calls this stall-free batching. The course simulator is faithful to it.

Why can a prefill chunk ride along nearly free? The Sarathi-Serve paper gives the mechanism in sections 3.1 and 4.1. Decode batches are memory-bound. The arithmetic units sit mostly idle while the weights stream from memory. A prefill is compute-bound. Its throughput already saturates around a 512-token sequence. So a modest prefill chunk fills compute units the decode batch was not using. Linear layers are more than 80% of runtime, even at high sequence lengths. The paper also measured median prompt sizes in two workloads. ShareGPT4: 1,730 tokens. Arxiv-summarization: 7,059 tokens. Prompts this size are routine. So the freeze is routine too.

Run the comparison with a larger prompt:

```bash
python phase02_internals/batching_sim.py --long-prompt 48000 --rate 10 --requests 60
```

Output on the author's machine, repeated on 2026-09-17 with the same result:

```
│ policy     │ mean TTFT │ p99 TTFT  │ mean TPOT │ worst gap  │ throughput │
│ static     │    8690ms │   14526ms │    19.5ms │       20ms │   2.7 rq/s │
│ continuous │    3028ms │    7140ms │    25.5ms │     1460ms │   3.8 rq/s │
│ chunked    │    3140ms │    7242ms │    24.9ms │       81ms │   3.8 rq/s │
```

Chunked prefill adds 3,140 - 3,028 = 112ms to mean TTFT. In return, the worst gap between two tokens falls from 1,460ms to 81ms. That is 18x smaller. It is the number your users feel during a stream.

The Sarathi-Serve paper measured this effect on real hardware. It mixed a prefill into a decode batch without chunking. Time between tokens rose by up to 28.3x compared with a decode-only batch. The conditions, from Figure 9: Mistral-7B on one A100 with a 256-token budget, and LLaMA2-70B on four A100s with a 512-token budget. Note the "up to". That is the freeze, measured on GPUs rather than simulated. The paper's abstract also reports serving capacity. 2.6x for Mistral-7B on one A100. Up to 3.7x for Yi-34B on two A100s. Both are measured against vLLM. Falcon-180B with pipeline parallelism reached up to 5.6x.

Chunking also has a cost, and the same paper measures one. Splitting a prefill repeats work at the chunk boundaries. So the setting has a lower limit. The phase quotes about 25% overhead at a 512-token budget on Yi-34B, from section 5.4.1. The study run could not re-open that section before its text cut off. So the direction is certain: small budgets cost throughput. The exact percentage is quoted, not re-verified. The paper's budget guidance sits in the same un-opened section. It is listed under "Things I could not verify".

The right budget depends on your product:

|                          | larger token budget     | smaller token budget  |
|--------------------------|-------------------------|-----------------------|
| TTFT for long prompts    | better                  | worse                 |
| inter-token smoothness   | worse                   | better                |
| good for                 | batch jobs, summarising | chat, voice, streaming|
| vLLM setting             | max_num_batched_tokens  | same setting, lower   |

The simulator shows the same trade in numbers. These runs use the default workload and change only `--token-budget`:

```
CHUNKED ROW vs TOKEN BUDGET (batching_sim.py, 40 requests, 6/s, measured)

  budget  worst gap                                            mean TTFT
  512     ██                                             35ms    1094ms
  2048    █████                                          81ms     925ms
  8192    ███████████████                               265ms     908ms
  none    ████████████████████████████████████████████  764ms     867ms
           (the "none" row is the continuous policy, with no chunking)
```

### What is the budget actually set to when you self-host?

Carry this into Phase 4. `max_num_batched_tokens` has no single default in vLLM 0.29.0. The constant `DEFAULT_MAX_NUM_BATCHED_TOKENS` in `vllm/config/scheduler.py` is 2048. Its own docstring says it exists "mainly for convenience when testing". Real values come from `EngineArgs.create_engine_config`. Chunked prefill itself is on: `enable_chunked_prefill: bool = True`. The startup choice lives in `get_batch_defaults()` in `vllm/engine/arg_utils.py`. It depends on the GPU class. It also depends on whether you run the offline `LLM` class or the API server. Verified against the v0.29.0 source tree:

| GPU class (device check)              | API server | offline `LLM` class | max_num_seqs |
|---------------------------------------|-----------|---------------------|--------------|
| B200/B300 (≥160GB)                    | 16,384    | 16,384              | 1,024        |
| H100/H200 (≥70GB, not A100)           | 8,192     | 16,384              | 1,024        |
| everything else, including A100       | 2,048     | 8,192               | 256          |

Three details bite. First, the A100 is excluded from the high tier by name. The source cites it directly: "Setting large max_num_batched_tokens for A100 reduces throughput, see PR #17885." So an A100 gets 2,048 through the API server but 8,192 through the offline class. The sentence "the A100 default is 2,048" is true in only one entry point. Second, `performance_mode` set to `"throughput"` doubles both defaults when you set neither yourself. Third, TPU and CPU have their own tables. The V6E TPU branch overrides only `max_num_batched_tokens`: 2,048 through the offline `LLM` class and 1,024 through the API server. It never sets `max_num_seqs`, so that stays at the generic tier's 256. None of these numbers travels to a non-GPU runtime.

Two more flags from the same v0.29.0 files change what you see in production:

- `scheduler_reserve_full_isl: bool = True` checks that the full input sequence fits in the KV cache before admitting a request. It prevents over-admission and KV-cache thrashing when chunked prefill is on. This ties back to part A's preemption section. Chunked prefill changes admission behaviour. This flag is the guard.
- `verify_max_model_len` raises a `ValueError` if `max_num_batched_tokens < max_model_len` while chunked prefill is disabled. That is the concrete error for the classic misconfiguration: a budget smaller than the prompt.

### What this means on a hosted API, and a gap that is not a stall

You cannot set `max_num_batched_tokens` on another company's server. You still see the effect. You can act on it in two ways:

1. Record inter-token gaps, not only TTFT and total time. An average does not show a frozen stream.
2. Keep your own prompts smaller. Your large prefill freezes other users' streams. On a single-tenant deployment, it freezes your own.

Before you blame a prefill, rule out two other causes of a lumpy stream. Both are verified in the v0.29.0 source:

- `stream_interval: int = 1` is the interval, in tokens, at which the server emits streamed output. The default of 1 is smooth. A larger value such as 10 cuts host overhead by batching tokens before sending. The two failure patterns look different. A prefill stall is irregular. A `stream_interval` of 10 is a steady burst-then-wait pattern. If you see the second one, do not tune `max_num_batched_tokens`. The fix is one config line elsewhere.
- vLLM can bound its waiting room with `max_num_queued_reqs` and `max_num_queued_tokens`. Both default to `None`, meaning off. When the queue overflows, vLLM rejects with HTTP 503. The source documents `max_num_queued_tokens` as a TTFT quality valve, sized as `target_TTFT × prefill_throughput`. It counts conservatively: a partially prefilled request counts its full prompt length until it starts producing tokens. So a 503 from your own vLLM is this valve opening. It is not a provider outage.

**The trap:** teams measure TTFT and total latency and call the stream healthy. Neither number shows an 800ms freeze in the middle of an answer. Add a maximum inter-token gap metric before you promise a streaming experience.

**Three things to internalize:** (1) decodes take the budget first, so the chunk size is `budget - n_decodes`, not `budget`. (2) smaller budgets trade TTFT for smoothness, so the budget is a product decision. (3) on vLLM 0.29.0 the "default" comes from the GPU class and entry point, so read `get_batch_defaults()` before you quote one.

**Try this now:** run `python phase02_internals/batching_sim.py --token-budget 512` and then `--token-budget 8192`. In the `chunked` row, mean TTFT and worst gap move in opposite directions. Expect 1,094ms and 35ms at 512, and 908ms and 265ms at 8,192.

**Verify:** the `chunked` row shows worst gap 35ms at budget 512 and 265ms at 8,192. Mean TTFT moves from 1,094ms down to 908ms. If your numbers differ, check you are on the same workload: 40 requests at 6/s.

**In Mission HQ:** open `backend/src/hq/obs.py` and find `emit()`. Which event would you add to record a per-run maximum inter-token gap? Where on the run path would you timestamp each token?

---

## 2.5 Does a schema guarantee your answer, or only its shape?

Why this matters: in Phase 1 exercise E11, a truncated JSON answer broke your parser. The lesson there was `finish_reason`. This section covers the other half. A prompt that asks for JSON is a request, not a guarantee. Constrained decoding makes the shape a guarantee. It also changes the output in ways most teams never measure. And the guarantee itself is weaker than the word suggests.

### How the server enforces a schema

Decoding picks one token at a time. Before each pick, the model gives a score to every token in the vocabulary. These scores are called logits. Sampling then chooses one token.

Constrained decoding adds a step between those two. It finds every token that would break the schema. It sets the score of each of those tokens to negative infinity. Those tokens then have zero probability. The model can only choose a legal next token.

```
ONE DECODE STEP, WITH AND WITHOUT A GRAMMAR MASK (example scores)

  model logits        mask (from the schema)      masked logits
  ┌──────────────┐    ┌──────────────────┐        ┌──────────────┐
  │ "Sure"  4.1  │    │ illegal here  ✗  │   →    │ "Sure"  -inf │
  │ "{"     3.8  │    │ legal         ✓  │   →    │ "{"      3.8 │  ← chosen
  │ "Here"  3.5  │    │ illegal here  ✗  │   →    │ "Here"  -inf │
  │ "["     2.9  │    │ illegal here  ✗  │   →    │ "["      -inf │
  └──────────────┘    └──────────────────┘        └──────────────┘

  The state machine now moves to "expecting a key or }". The next step gets a
  different mask. Prose can never appear, because prose tokens are never legal.
```

The mask comes from a state machine. The engine builds it from your schema in three steps:

1. It reads your JSON Schema or grammar.
2. It builds the states.
3. For each state, it computes which vocabulary tokens are legal.

Three libraries do this work today: Outlines, XGrammar and llguidance. JSONSchemaBench benchmarks the third one as Guidance. vLLM and SGLang use these libraries inside. XGrammar gets its speed by precomputing. The MLC blog reports that under typical schemas, more than 99% of tokens are context-independent. Their legality can be computed once, before generation starts, into an adaptive token mask cache. The blog reports up to 3.5x faster mask generation on JSON schema and up to 10x on context-free grammars. The comparison baseline: Outlines v0.1.3/v0.0.45, llama-cpp b3998 and lm-format-enforcer v0.10.9, on Llama-3-8B and Llama-3.1-8B.

Building the state machine takes time. The time differs wildly by library. JSONSchemaBench measured median grammar compilation time (GCT) on the same schemas. On the HF Transformers backend with Llama-3.1-8B-Instruct (its Table 3): Guidance compiles in a 0.01s median across all four suites. XGrammar takes 0.11s to 0.30s. On the llama.cpp backend (its Table 2): Guidance takes 0.00s to 0.01s, Llamacpp 0.05s to 0.06s, and Outlines 3.48s to 8.05s median.

| library  | median grammar compile time | conditions |
|----------|-----------------------------|------------|
| Guidance  | 0.01 s                    | HF Transformers, Llama-3.1-8B-Instruct, all four suites |
| XGrammar  | 0.11–0.30 s               | same |
| Guidance  | 0.00–0.01 s               | llama.cpp backend |
| Llamacpp  | 0.05–0.06 s               | llama.cpp backend |
| Outlines  | 3.48–8.05 s               | llama.cpp backend |

The last number is the one that matters operationally. JSONSchemaBench adds that features like `minItems`, `maxItems`, `enum` and `Array` are supported by Outlines, but often take 40 seconds to 10 minutes to process. The gap between the fastest and slowest backend medians is around 70x. XGrammar hides much of its cost by compiling at the same time as the prefill.

**The first-request delay on OpenAI applies to every model.** The current structured outputs page, read in full on 2026-09-19, states: "the first request you make with any schema will have additional latency as our API processes the schema, but subsequent requests with the same schema will not have additional latency." There is no fine-tuned-model carve-out on the current page. The fine-tuned distinction there is about keyword support, not latency. So on any hosted provider, treat a new schema as a possible slow first call. Measure it. The lab's Try-this-now does exactly that.

### The three levels, and what each one promises

|                    | prompt only       | json_object      | json_schema strict: true |
|--------------------|-------------------|------------------|--------------------------|
| valid JSON         | not guaranteed    | guaranteed       | guaranteed               |
| correct keys       | not guaranteed    | NOT guaranteed   | guaranteed*              |
| values within enum | not guaranteed    | not guaranteed   | guaranteed*              |
| prose wrapping     | happens           | cannot happen    | cannot happen            |
| first-call cost    | normal            | normal           | engine compiles the grammar |
| can still truncate | yes               | yes              | yes                      |

The asterisk is real. On hosted strict APIs the guarantee holds, because the provider fully enforces the schema. On self-hosted engines it depends on the backend. JSONSchemaBench's Table 6 counts failure modes on the JSON Schema Test Suite. XGrammar shows **38 categories of under-constrained failures**. That means it allows instances the schema says are invalid. The other libraries show far fewer: Guidance 1, Outlines 8, Llamacpp 7. The paper's reading: XGrammar trades strictness for permissiveness. It is also the fastest engine. If your vLLM default `auto` path picks XGrammar, "the shape is guaranteed" is an assumption to test, not a property. Keep an upstream validator on the critical path until you have tested it.

Read the last row of the table twice. A schema controls which tokens are legal. It does not control when generation stops. Suppose `max_tokens` runs out in the middle of an object. You get a truncated document. It still follows the schema's shape. It still cannot be parsed. Only `finish_reason` tells you this happened. Phase 1 E11 is that failure. Strict mode does not remove it.

One more result changes the cost story. JSONSchemaBench's Table 2 shows Guidance TPOT of 6.4ms to 9.5ms, against 15.3ms to 16.7ms for unconstrained generation. The conditions: batch size 1, one A100-80GB, Llama-3.1-8B-Instruct, on the llama.cpp backend. Constrained decoding was **faster** per token there. Guidance acceleration skips steps, and the schema forbids wasted prose. The paper's introduction reports speedups of up to 50% from constrained decoding. Treat this as batch-1, that-model, those-schemas evidence. On latency, structured output is not a pure cost. The quality question is the next part.

### The constraint tax: does the schema make the answer worse?

Forcing a schema can change the quality of the answer, not only its shape. Researchers disagreed about this for two years. A 2026 paper explains the disagreement.

**The original claim.** A 2024 EMNLP paper, "Let Me Speak Freely?", reported large drops on reasoning tasks:

- On GSM8K, claude-3-haiku scored 86.99 in plain JSON mode. It scored 23.44 with a schema constraint.
- gpt-3.5-turbo fell from 74.70 to 49.25.

Two details matter. First, the standard deviations were very large: 22.9 and 12.0 across 9 prompts. Second, the paper's own appendix shows constraints helping classification tasks. On DDXPlus, gemini went from 41.6 to 60.3. claude-3-haiku went from 33.8 to 52.0.

**The rebuttal.** The authors of Outlines ran the same model and tasks again. They measured the opposite:

- GSM8K: 0.77 unstructured and 0.78 structured.
- Last Letter: 0.73 and 0.77.

They also raised an objection. The original paper never confirmed that a provider's JSON mode uses grammar-constrained decoding. The paper says only that it "is assumed". A third benchmark, JSONSchemaBench, also measured small gains.

**The 2026 answer.** A paper called "The Format Tax" tested 6 open-weight and 4 closed-weight models. It used 4 formats and 4 tasks. It split the drop into two causes. Its abstract, verified on 2026-09-19, states three things. The dominant cost comes from the format-requesting prompt, not from constrained decoding. Decoupling the format from the reasoning recovers most of the accuracy: answer freely, then reformat, or use extended thinking. And recent closed-weight models show little or no tax at all.

The numbers below come from the paper's body. The phase re-checked them on 2026-09-17. This study run verified the abstract only, so they stand on the phase's check. See "Things I could not verify".

- Asking for a format in the prompt cost 3.9 points on average.
- Adding grammar-constrained decoding on top cost 1.6 points on average.
- 39 result cells had a statistically significant effect. In 36 of them, the effect was already present from the prompt alone. Only 3 cells showed a drop from constrained decoding alone.

```
WHERE THE FORMAT TAX COMES FROM (The Format Tax, average points lost, as
reported in the paper's body)

  format request in the prompt    ████████████████████████████████████████  3.9
  constrained decoding on top     ████████████████                          1.6
```

Two more results from the same body are useful to you:

- Three newer closed-weight models showed changes near zero or above zero without constrained decoding: claude-haiku-4.5, grok-4.1-fast and gpt-5.4-nano. claude-haiku-4.5 scored +1.2 and grok-4.1-fast +2.5 against their own free-form baselines. The older gpt-5-nano still lost 5.2 points without constrained decoding and 8.0 with it. Small open models lost 5 to 9 points. So the claim "structured output costs X percent" is wrong unless it names the model.
- Constrained decoding raised format validity from 55.7% to 92.2%. Accuracy moved from 57.3% to 55.7%. The free-form baseline was 61.5%. The paper's summary: "higher compliance does not translate into better reasoning".

**The scoring warning.** Every group in this debate hit the same problem: the parser changes the score.

- Tam et al. used a model to parse answers. Their own table shows the parser choice moving a score by up to 42 points.
- The Format Tax authors switched from a rule-based extractor to a model judge. Their average MATH-500 tax fell from 10.1 points to 6.6 points. About a third of the measured tax came from scoring.

When you measure your own tax, fix the parser first. Report it with the result. A number without its parser tells you nothing.

So measure it. `structured_lab.py` sends the same 12 labeled tickets through all three modes:

```bash
python phase02_internals/structured_lab.py --self-test     # no key needed
export OPENAI_API_KEY=sk-...
python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap
```

The script reports six values per mode: accuracy, parse failures, output tokens, mean latency, first-call latency and cost. The accuracy gap between `prompt` and `strict` is your constraint tax on this task. The gap can be negative. A negative gap means the schema helped.

### Why does the reasoning field have to come first?

Then test the standard fix:

```bash
python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --reasoning-field
```

This flag adds one free-text field to the schema, before the constrained fields. From `structured_lab.py:90`, docstring shortened, logic unchanged:

```python
def schema(with_reasoning: bool) -> dict:
    """JSON Schema for strict mode.

    The reasoning field is FIRST on purpose. Decoding is left to right, so a
    field can only influence fields that come after it.
    """
    props: dict = {}
    if with_reasoning:
        props["reasoning"] = {"type": "string",
                              "description": "one short sentence of justification"}
    props["category"] = {"type": "string", "enum": CATEGORIES}
    props["priority"] = {"type": "string", "enum": PRIORITIES}
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }
```

The property order is the point. OpenAI's page states: "When using Structured Outputs, outputs will be produced in the same order as the ordering of keys in the schema." If `reasoning` comes last, it changes nothing. The answer is already chosen by then. This rule has a mechanical reason and direct evidence:

```
WRONG: {"category": "billing", "priority": "high", "reasoning": "…"}
        the label is already locked before the reasoning token exists
RIGHT: {"reasoning": "one short justification …", "category": "billing", "priority": "high"}
        the label can condition on the reasoning
```

- Tam et al. found that 100% of gpt-3.5-turbo JSON-mode answers put the answer key before the reason key. That turns step-by-step reasoning into a direct answer.
- JSONSchemaBench used the opposite order. Its Table 8 has the exact result. On GSM8K with that ordering, LM-only scored 80.1%. Constrained decoding scored 83.7% with XGrammar and 83.8% with Guidance. Last Letter went from 50.7% to 53-54%. Shuffle went from 52.6% to 53-56%. Under that ordering, constrained decoding **beat** unconstrained decoding on all three tasks.

The Format Tax also measured two other fixes, in the body numbers the phase checked:

| mitigation                              | improved  | made worse     | average gain |
|-----------------------------------------|-----------|----------------|--------------|
| two calls: answer freely, then reformat | 42 of 72  | 2 of 72 (3%)   | +6.8 points  |
| thinking enabled before the structured answer | 43 of 72 | 11 of 72 (15%) | +9.2 points |

Two calls is the safer choice. It costs one extra request. Thinking gives a larger gain on maths and does not help on writing. Neither fix is free. Measure before you pick one.

### Which schema limits does OpenAI enforce on day one?

**Three schema rules to get right on day one**, all verified against the current guide:

1. Every property must appear in `required`.
2. `additionalProperties` must be `false`.
3. To make a field optional, use a union with null, such as `"type": ["string", "null"]`. Do not leave the key out of `required`.

The page also lists size limits, every one verified on the current guide:

- The root must be an object. It cannot be `anyOf` or another composition. A Zod discriminated union at the root will not work.
- At most 5,000 object properties in total.
- At most 10 nesting levels.
- Property names, enum values and const values together must stay at or under 120,000 characters.
- At most 1,000 enum values total. Any single enum with more than 250 values is limited to 15,000 characters across its values.

The unsupported-keyword list has become shorter. Check the current page, not an older blog post. As of September 2026, these keywords are supported for normal models only: `pattern`, `format` (date-time, time, date, duration, email, hostname, ipv4, ipv6, uuid), `multipleOf`, `maximum`, `exclusiveMaximum`, `minimum`, `exclusiveMinimum`, `minItems` and `maxItems`. Fine-tuned models do not support them yet. Fine-tuned models also lack `minLength`, `maxLength` and `patternProperties`. These composition keywords are unsupported for all models: `allOf`, `not`, `dependentRequired`, `dependentSchemas`, `if`, `then`, `else`. Some other keywords do not appear on the page at all. Their status is not documented. Test such a keyword before you depend on it.

### What happens when your serving engine picks the backend for you?

When you serve the model yourself, the engine picks a grammar backend. Phase 4A section 4.2 covers the configuration. The behaviour matters now, because it changes both errors and latency:

- vLLM defaults to `auto`. It checks your schema against XGrammar first. If a keyword is unsupported, it falls back to Guidance, then to Outlines. The course verified this against v0.29.0 on 2026-09-12. The fallback order was not re-opened this study run.
- If you pin one backend instead, the same unsupported keyword becomes an error.
- SGLang 0.5.19 defaults to XGrammar. It has no per-schema fallback.

The compile times above differ by up to ~70x between backends. So a silent backend switch is a latency change. The same schema moves from 0.01s to 3.5s or worse. And it is also a correctness change. A schema that Guidance enforces exactly, XGrammar may enforce loosely. A backend fallback is never silent in its effects. It is silent only in your logs.

**The sentence to remember:** constrained decoding masks illegal tokens at every step. On a hosted strict API the shape is guaranteed. On self-hosted engines the guarantee depends on the backend. The stopping point is never guaranteed. The effect on quality is yours to measure.

**The trap:** an older article may tell you the decoder's constraints are the expensive part. The 2026 evidence says the prompt asking for the format is the dominant cost. A schema can even speed generation up by forbidding prose. Measure the tax on your model, your task and your parser. Expect a possible slow first call on any new schema.

**Three things to internalize:** (1) the reasoning field goes first, because decoding is left to right. (2) `required` holds every key, `additionalProperties` is false, optional means union with null. (3) report every tax number with its model, its parser and its date.

**Try this now:** run `python phase02_internals/structured_lab.py --model gpt-4.1-mini --modes strict --repeat 3`. Compare the `first call` column with the `mean lat` column. The current OpenAI page says the first request with any new schema pays the compile cost, on any model. So do not promise yourself a gap of zero. Record the gap you measure, with the date.

**Verify:** all six parser self-tests pass first: `--self-test` ends with "all self-tests passed". In the live run, `strict` shows zero parse failures. Write the `first call` and `mean lat` numbers down for Phase 5B.

**In Mission HQ:** open `backend/src/hq/tools/registry.py` and find the `@hq_tool` decorator. If a tool's return had to be schema-constrained JSON, where would the schema live? Which existing validation error would fire when the answer truncated?

---

## 2.6 How do you stop a long run dying on a 400?

Why this matters: Phase 1 exercise E7 sent a prompt that was too large and got a 400 back. That exercise promised the fix in this section. The fix is more than a try and except block. It is a budget, a trigger, an explicit choice about what survives compaction, and a backstop for when the trigger is wrong.

The context window is the maximum number of tokens the model accepts in one call. Compaction replaces old conversation turns with a shorter summary. The prompt fits again. Everything in this section answers two questions. When do you compact? And what crosses the boundary?

### First, why a bigger window does not solve this

You might think a one million token window ends the problem. It does not. There are three separate reasons. Each one has evidence.

**Reason 1: accuracy falls as input grows.** Chroma's context rot study tested 18 models from the Claude, GPT, Gemini and Qwen families. It ran simple retrieval tasks at many input lengths. Performance fell as length grew, in every family. The study also ran a LongMemEval test. Every model scored higher on a focused input of about 300 tokens. The full input had about 113,000 tokens and contained the same answer.

**Reason 2: position inside the window matters.** The Lost in the Middle study moved the needed document to different positions. It measured accuracy at each position. Its prose states that performance "can drop by more than 20%". With 20 or 30 documents, mid-context accuracy fell **below** the closed-book score. That score was 56.1% for GPT-3.5-Turbo: the model did worse with the answer buried in a long prompt than with no documents at all. The phase's exact figures, 75.8% for first position and 53.8% for middle position, are readings of Figure 5. They are consistent with the prose, but not stated in it. The models are from 2023: GPT-3.5-Turbo 0613, Claude-1.3, MPT-30B-Instruct, LongChat-13B. Treat the numbers as the shape of the effect. One verified result from the same paper sharpens reason 1. The extended-context variants, GPT-3.5-Turbo-16K and Claude-1.3-100K, performed nearly identically to their short-window counterparts on the shorter inputs. A bigger window did not make the model better at using the tokens it already had.

**Reason 3: a full large window is expensive.** Cost grows with every input token. A 400,000-token prompt on every step of a 50-step loop is 20 million input tokens. The `deep` role in `prices.yaml` is gpt-4.1 at $2.00 per million input tokens. So one conversation costs 20 × $2.00 = $40.

So a larger prompt costs more for every extra token. And each extra token helps less.

### The budget: zones with caps

A context window has a fixed size. Several sources write into it. Without caps, the largest source takes the space. The largest source is usually a tool that returned a large result. So split the window into zones. Give each zone a cap.

```
┌──────────────────────────────────────────────────────────────────┐
│ CONTEXT BUDGET for a 32,000-token window (example caps)          │
├──────────────────┬───────────┬───────────────────────────────────┤
│ zone             │ cap       │ rule                              │
├──────────────────┼───────────┼───────────────────────────────────┤
│ system           │   1,000   │ never changes; first in prompt    │
│ tools            │   6,000   │ changes on deploy only            │
│ carry-over       │   2,000   │ written by compaction             │
│ history          │  10,000   │ oldest turns leave first          │
│ retrieval/tools  │   6,000   │ truncate results, keep pointers   │
│ headroom for the │   7,000   │ the reply needs room, and so does │
│ answer           │           │ the summarising call              │
└──────────────────┴───────────┴───────────────────────────────────┘
```

The zone order follows the prefix rule from part A section 2.3. Stable content first, so the longest prefix stays cacheable. People forget the headroom row most often. If you fill the window to the limit, the summarising call cannot run either. That call is the one that would fix the problem.

### The trigger: compact early, at a threshold you chose

Do not wait for the error. Count the tokens before every call. Compact when the total passes a threshold that you set.

Shipped products set thresholds well below the window:

- Anthropic's context editing tool (`clear_tool_uses_20250919`) clears old tool results at a default trigger of 100,000 input tokens. It keeps the last 3 tool uses. Verified on the current docs.
- Anthropic's server-side compaction feature (`compact_20260112`, beta header `compact-2026-01-12`) defaults to a trigger of 150,000 input tokens. It rejects values below 50,000. Verified on the current docs.

Both use the same pattern: a fixed number, chosen in advance, below the limit. The docs carry two adjacent mechanisms worth knowing. A second editing strategy, `clear_thinking_20251015`, clears thinking blocks. Its defaults vary by model class. And the response carries `context_management.applied_edits`. That field reports exactly what was cleared, so your logs see the edit instead of inferring it. One cost note: clearing tool results invalidates cached prompt prefixes. Part A's prefix cache rewards a stable prefix. An edit in the middle breaks everything after it. Phase 3A prices this properly.

A newer idea is worth knowing. The Self-Compacting Language Model Agents paper argues that a token threshold can fire at a bad moment. For example, in the middle of a derivation. The paper lets the model decide instead, with a rubric. Compact when a sub-task ends. Never compact mid-derivation or while stuck. It reports up to 18.1 points higher on math benchmarks, 5 to 9 points higher on agentic search, and 30 to 70 percent lower cost per question. Treat this as a likely future direction. Start with a threshold. A threshold is simple, and you can test it.

This is how the course's `compactor.py` behaves with its default threshold of 60% of a 32,000-token window:

```bash
python phase02_internals/compactor.py --simulate --turns 40
```

The trigger fires at turn 25. The run was repeated on 2026-09-17 with the same result:

```
  24 │     18,631 │
  25 │     19,409 │ trigger fired
    COMPACTED (threshold): 19,409 -> 2,270 tokens, 45 turns summarised, 4 kept verbatim
  25 │      2,270 │
```

The trigger is at 32,000 × 0.60 = 19,200 tokens. Turn 25 is the first turn above it. Note one detail of the output. The script counts every history message as one "turn". Each loop turn adds a user message and an assistant reply. So at loop turn 25, the history holds 24 × 2 + 1 = 49 messages. 45 are summarised. 4 are kept.

### What to keep, and the number that shows why

A summary keeps what the summariser found interesting. That is where it fails. A later turn cannot recreate three kinds of facts: decisions, constraints and open items.

Constraints are the most dangerous to lose. The "Governance Decay" paper shows why. It built a benchmark called ConstraintRot. It ran 1,323 episodes across seven model families. Each episode stated policy constraints in the context. A program graded the tool calls, not a model. The results, verified against the abstract on 2026-09-19:

- With the policy fully visible, the violation rate was 0%.
- After compaction, it rose to 30%, and reached 59% for some models.
- When the constraint survived the summary, violations stayed at 0%. When the summary dropped it, violations were 38%.
- The paper's fix is Constraint Pinning: constraints stay out of the lossy summary. Violations returned to 0%.

The same paper documents something worse than loss. **Compaction is an attack surface.** Its Compaction-Eviction Attack plants adversarial content inside the context. The content biases the summariser into dropping a legitimate policy. The optimized injections defeated every model evaluated. So a prompt-injection payload near the summarisation boundary can evict the very rule that governs the agent. The defence is the same rule as for honest loss. Do not let a language model decide whether your safety rule is worth keeping. Copy constraints across the boundary as literal text, outside the summarised region.

```
COMPACTION BOUNDARY — what crosses it (compactor.py --simulate, loop turn 25)

  BEFORE (19,409 tokens)                AFTER (2,270 tokens)
  ┌─────────────────────────┐           ┌─────────────────────────┐
  │ system                  │──verbatim→│ system                  │
  │ tools                   │──verbatim→│ tools                   │
  │ message 1  ─┐           │           │ [COMPACTED]             │
  │ message 2   │           │           │  Summary: ...           │
  │  ...        ├ summarised┼──────────→│  Decisions: ...         │
  │ message 44  │           │           │  Constraints: COPIED    │
  │ message 45 ─┘           │           │  Open items: ...        │
  │ message 46 ─┐           │           │ message 46              │
  │ message 47  ├ kept      ┼──verbatim→│ message 47              │
  │ message 48  │           │           │ message 48              │
  │ message 49 ─┘           │           │ message 49              │
  └─────────────────────────┘           └─────────────────────────┘
```

### Where this fails in production: the agent that forgets its own rules

This failure has public bug reports. Treat it as observed, not hypothetical. On 2026-02-09, `anthropics/claude-code#24460` reported the following. After running `/compact`, the project instruction file (CLAUDE.md) is summarised along with the rest of the history. That file holds commit conventions, push procedures and security rules, and it can be lost. The reporter observed this with Claude Opus 4.6. The ask: re-inject the instruction file after compaction. The issue was closed as not planned. The documented workaround is to tell the agent to re-read the file after each compact. An earlier report, `#19471` from 2026-01-20, describes the same symptom: instructions "completely ignored" after a context compaction boundary.

Note the shape. The mitigation users discovered by hand is exactly Constraint Pinning. A rule that must hold crosses the boundary as literal text. You copy it. The summariser does not choose it.

### Anthropic now ships the pinning pattern in the API

Besides the threshold mode `compact_20260112`, Anthropic's docs describe an **on-demand** mode behind beta header `compact-2026-09-04`. Verified 2026-09-19:

1. You send `compaction: {type: "summarize"}` on a request.
2. You get back a single signed compaction block, with `stop_reason: "compaction"` and no normal reply.
3. You keep that block intact. You send it **first** on every later request. Leaving summarized messages in front of it is a 400, code `compaction_block_misplaced`.

Three details make this directly useful. `pause_after_compaction` returns `stop_reason "compaction"`, so the client can insert blocks before the conversation resumes. That is the API-level version of "copy constraints across the boundary". The boundary is handed back to you. An `instructions` field replaces the default summarisation prompt entirely. You can tell the summariser to always preserve a named section. And the limits matter. The same model does the summarising; there is no cheaper model. Images, documents and fetched URLs are lost once summarized and must be re-uploaded. With tools defined, the model may call a tool mid-summarisation and return a compaction block with `content: null`. The docs recommend instructions forbidding that. On-demand compaction is Claude-API only. It cannot be combined with `context_management` on the same request.

One caution on the phase's blanket claim "Anthropic sends no error code". That sentence is about context-overflow errors. Anthropic does document the 400 `compaction_block_misplaced` code above, for compaction misuse. Also: SDK-based client-side compaction is removed in the Python SDK v1.0. The server-side feature replaces it. The docs name one more real trigger bug. Server-side tools like web search inflate `cache_read_input_tokens` across internal calls. An SDK-side context estimate can then pass the threshold early. Your compactor fires too soon. If your trigger fires before your own token count says it should, this is the first suspect.

### The backstop: catch the 400, compact, retry once

The trigger can still be wrong. A tool can return far more than you expected. Keep a second layer. Make it log loudly.

```python
# WRONG: the classic retry. It resends the SAME oversized prompt.
# The provider rejects it again, in about the same time, for the same reason.
for attempt in range(3):
    try:
        return client.chat.completions.create(model=m, messages=msgs)
    except Exception:
        time.sleep(2 ** attempt)        # waiting changes nothing here

# RIGHT: change the input, then retry exactly once.
try:
    return client.chat.completions.create(model=m, messages=msgs)
except Exception as e:
    if not is_context_overflow(e):
        raise
    log.error("compaction trigger missed; backstop fired")   # this is a bug report
    msgs = compact(msgs)                                     # the input changed
    return client.chat.completions.create(model=m, messages=msgs)
```

This pair is a short illustration. The shipped version of the RIGHT pattern is in `compactor.py:660` to `compactor.py:671`. Phase 1 E7 describes the wrong version's result: a fast 400 rejection that a blind retry cannot fix.

Detect the error by its machine-readable fields, not by its wording. The stable parts are HTTP status 400, an error `type` of `invalid_request_error`, and an error `code` of `context_length_exceeded`. The phase's 2026-09-17 check found that OpenAI's public error-codes page does not list this error at all. So any exact message text you hardcode today can change without notice. `is_context_overflow` at `compactor.py:227` shows the order of checks. Status first. Then code. Then error type. Message text last. A 429 or a 5xx is never an overflow, even when its text looks like one. For Anthropic, the phase's 2026-09-17 check found that an oversized input returns a 400 `invalid_request_error` with the text "prompt is too long", and no error code. The function matches that by type and text. This study run did not re-open either error page. Both error shapes stand on the phase's check.

Now run the same loop without the trigger:

```bash
python phase02_internals/compactor.py --simulate --turns 60 --no-compaction
```

```
  41 │     31,857 │
  42 │     32,635 │ STOP: prompt exceeds the window. This is the E7 failure.
```

Turn 42 is where the Phase 1 exercise ended. With the trigger on, the run never reaches that point.

### The known limits of compaction

Compaction is not a solved problem. Be careful with any source that says it is. These studies were not re-opened by this study run. The phase checked their abstracts on 2026-09-17.

- **Compaction can lower accuracy.** The Slipstream paper describes a validation gap. The compactor must shorten the context without knowing what the agent will need later. It validates candidate summaries outside the main request path. It reports up to 8.8 percentage points of accuracy recovered and up to 39.7% lower end-to-end latency.
- **Repeated compaction makes runs less stable.** TRACE, an August 2026 study from the University of Virginia and Nokia, used the AppWorld benchmark. It found that compression weakens the effect of recent turns. The agent then hits more blocked actions and repeats more work. Results also vary more between runs.
- **Long tasks fail for reasons beyond token count.** A study of 10,664 trajectories across nine models measured this. Task success fell with the number of steps, not with the context length. A smaller context window made success fall faster, not slower. Reliability per step rises with model size, but it stays below 1. A long enough task fails anyway.
- **Compaction is billed.** Anthropic's compaction feature runs as a separate sampling iteration. "Top-level input_tokens/output_tokens exclude compaction-iteration usage", verified on the current docs. The real total needs a sum across `usage.iterations`. Your own summarising call has the same property. It is a second call. Your cost meter must count it.

**The sentence to remember:** compact at a threshold you chose. Copy constraints across the boundary as literal text. Treat a 400 as a bug in your trigger, not as a normal event.

**The trap:** anything a summary drops is gone for good. When the summary drops a policy constraint, measured violations jump from 0% to 38%. An attacker can also place content that makes the summariser drop it on purpose. Decide what to copy word for word before you decide what to summarise.

**Three things to internalize:** (1) the trigger fires below the window, with headroom for the reply and the summarising call. (2) constraints cross the boundary verbatim; decisions and open items are summarised; tool results are dropped to pointers. (3) the backstop changes the input and retries exactly once, detected on fields in order: status, code, type, text.

**Try this now:** run `python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5` and read the backstop lines. Then open `compactor.py:670`. Confirm that `cm.compact` changes the input before the retry on line 671.

**Verify:** call 5 fails with a context-length error. The backstop compacts from 3,849 to 2,270 tokens. One retry succeeds. The run continues. The summary line reports `backstops: 1`.

**In Mission HQ:** open `backend/src/hq/safety.py` and read the budget and HALT checks. If an agent run ever compacted its instruction context, which checks survive as code? Which one would you pin verbatim?

---

## The lab: measure the freeze, the tax and the trigger

Setup: `cd ~/Desktop/project/code/study-material/inference-internals/code && pip install -e .`

Three of these six exercises need no API key and no GPU. They are marked "offline". The rest need `export OPENAI_API_KEY=sk-...` or another OpenAI-compatible endpoint through `--base-url` and `--key-env`.

**Run status:** every offline command below was run on 2026-09-17, and the output matched the numbers printed here. The API-calling commands were not run against OpenAI, because no API key was available on this machine on 2026-09-12. The command flags were checked against the shipped scripts. So E8, E9 and E10 are marked UNVERIFIED against a live provider. Run them and record what you see. One corrected expectation: per the current OpenAI structured outputs page, the first request with any new schema pays a compile cost on **any** model, so a visible first-call gap in E8–E10 is the documented behaviour, not a surprise.

**Exercise numbers:** part B holds E4 and E8 to E12. The numbers are the same as in the original single Phase 2 document, because other phases cite them. E1, E2, E3, E5, E6 and E7 are in part A.

Record every number. Phase 5B uses your gap measurements.

### E4 (offline). Find the token budget trade.

- Run: `python phase02_internals/batching_sim.py --token-budget 512` then `python phase02_internals/batching_sim.py --token-budget 8192`.
- Expected, in the `chunked` row: mean TTFT 1,094ms and worst gap 35ms at 512. Mean TTFT 908ms and worst gap 265ms at 8,192. The two numbers move in opposite directions.
- Then read the limit of the model. The simulator does not model chunking overhead. Sarathi-Serve measured overhead at small budgets (the phase quotes about 25% at a 512-token budget on Yi-34B; the exact figure was not re-verified this study run). A very small budget has a real throughput cost.
- Teaches: `max_num_batched_tokens` is a product decision. Chat and batch jobs want opposite settings.

### E8 (live, UNVERIFIED against a live provider). Measure the constraint tax on a real task.

- Run offline first: `python phase02_internals/structured_lab.py --self-test`. Confirm that all six parser cases pass and the last line is "all self-tests passed".
- Then run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap`
- Expected: `prompt` mode records at least one parse failure across 12 tickets. `json` and `strict` record zero. The accuracy column shows your tax. The tax can be positive or negative.
- Costs at most: about $0.02 for all three modes.
- Teaches: the shape guarantee and the quality question are two different things.

### E9 (live, UNVERIFIED against a live provider). Test the reasoning field.

- Run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --reasoning-field`
- Expected: output tokens, cost and latency rise. Accuracy may or may not rise. Compare with E8, and decide whether the trade is worth it on this task.
- Teaches: a free-text field before the constrained fields is a change you can measure.

### E10 (break-it, live, UNVERIFIED against a live provider). Truncate an answer that follows the schema.

- Run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --modes strict --reasoning-field --max-tokens 15`
- Expected: the `truncated` column fills up. Parse failures appear, even though every answer followed the schema until it stopped.
- Teaches: a strict schema guarantees legal tokens, never a complete answer. `finish_reason` is still required, as Phase 1 E11 said.

### E11 (offline). Watch the compaction trigger fire.

- Run: `python phase02_internals/compactor.py --simulate --turns 40`
- Expected: the prompt grows to 19,409 tokens and the trigger fires at turn 25. The prompt drops to 2,270 tokens. The script reports 45 turns summarised and 4 kept verbatim.
- Then run it with `--trigger-ratio 0.3`. Expected: the trigger moves to 9,600 tokens and fires three times, at turns 13, 23 and 33.
- Then run it with `--keep-last 10`. Expected: one compaction at turn 25, down to 4,604 tokens, with 10 kept verbatim.
- Teaches: the trigger is a number you choose. The token counts show the effect of that choice.

### E12 (break-it, offline). Reproduce Phase 1 E7, then catch it.

- Run: `python phase02_internals/compactor.py --simulate --turns 60 --no-compaction`
- Expected: the run stops at turn 42 with 32,635 tokens and the line "STOP: prompt exceeds the window. This is the E7 failure."
- Then run: `python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5`
- Expected: call 5 fails with a context-length error. The backstop compacts from 3,849 to 2,270 tokens, one retry succeeds, and the run continues. The summary line reports `backstops: 1`. The next line tells you to lower `--trigger-ratio`.
- Teaches: the trigger is the fix. The backstop is the second layer. A backstop that fires is a bug report.

## Check it yourself: questions against the course code

This course has no anchor repository. These questions use the exercise code you now have. The last question works on any repository.

1. Open `code/phase02_internals/compactor.py:142`. This is `ContextManager.render`. It joins the zones in a fixed order. Explain why moving `self.carry.render()` above the tools block would raise your bill. Use section 2.3 from part A. Then open `CarryOver` at line 98. Find the one field that the ConstraintRot results say must never depend on the summariser.
2. Open `code/phase02_internals/compactor.py:227`. This is `is_context_overflow`. List the checks in order. Then find the first `return False`. Explain what the function returns for a 500 error whose message contains "maximum context length". Say why that answer is safe for a retry loop.
3. Open `code/phase02_internals/batching_sim.py:122`. In chunked mode, `room` subtracts `len(decoding)` before any prefill is taken. Suppose the prefill took the budget first, and the decodes got what was left. Predict what happens to the worst gap. Explain which user sees the difference.
4. In any service you own that calls a model, run `grep -rn "max_tokens\|finish_reason\|response_format" <your repo>/`. For every call that sets `response_format` but never reads `finish_reason`, write down what happens when the answer is cut off.

## Checkpoint 2B: answer in your own words

1. **This is broken.** Your streaming support answers look fine on the dashboard. Median TTFT is 600ms and median total time is 4.2s. Users report that the text "stops for a second" in the middle. Nothing in your metrics shows it. (a) Name the server behaviour from section 2.4 that causes this. (b) Name the one metric you must add. (c) Your provider will not change its token budget for you. Name two things you can still change.

2. **Walk through what happens, and show the arithmetic.** A server uses the cost model from `batching_sim.py`. Three requests are decoding. A 24,000-token prompt arrives. The token budget is 2,048. (a) How long do the three streams freeze without chunking? (b) With chunking, how many tokens of prefill fit in each iteration, and how many iterations does the prompt need? (c) How long is each chunked iteration?

3. **This is broken.** Your classification service returns valid JSON that matches the schema on every call. `finish_reason` is `stop`. But accuracy dropped 9 points after you enabled strict mode last week. (a) Give the most likely cause from section 2.5. (b) Describe the exact schema change you would test, including its place in the property order. (c) Name the measurement that would settle it. Say why one run is not enough.

4. **Given these constraints, design** the context strategy. Your agent runs 200 tool-calling steps over several hours. A policy rule says it must never issue a refund above 200 EUR. Cover the trigger, the text you copy word for word, the summary, what you drop, and cost records. Use the ConstraintRot numbers to justify one choice.

5. **A colleague says:** "Compaction fixed our long-running agent. We compact at 60%, and tasks now finish." Give the counter-argument from the 2026 research in section 2.6. Name the finding about step count and context length. Say what you would measure to tell the two explanations apart.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) Another request's long prefill ran in one iteration without chunking. Every decoding request got no token during that pass. (b) The maximum inter-token gap per response, recorded while the stream runs. Median TTFT and total latency cannot show a freeze. On a self-hosted vLLM, first rule out a non-prefill cause: a uniform, regular gap pattern is `stream_interval` above 1 batching your tokens, not a stall. (c) Shorten your own prompts, so your prefills are small. Move long-context work to a separate endpoint or a batch path. Then it does not share a batch with interactive traffic. A fallback provider for interactive traffic is a third option.

2. (a) The prefill-only pass costs 24,000 × 0.03 = 720ms. The three streams get no token for that pass. With the decode passes on each side, the measured worst gap in the default run is 764ms. (b) The budget reserves 3 tokens for the decodes, so 2,048 - 3 = 2,045 prefill tokens fit per iteration. 24,000 / 2,045 = 11.7, so the prompt needs 12 iterations. (c) 2,045 × 0.03 + 18 + 0.12 × 3 = 61.4 + 18.4 = 79.8ms. The streams now pause about 80ms per token instead of 720ms once. The measured worst gap is 81ms, because the real batch holds more decodes.

3. (a) The schema forces the label early. The model chooses a label with no room to reason in text first. (b) Add a `reasoning` string field as the first property, before the constrained fields. Add it to `required`, and keep `additionalProperties: false`. A `reasoning` field placed last changes nothing, because decoding runs left to right. (c) Run the same labeled set through both schemas with `structured_lab.py`. Fix and report the parser. One run is not enough, because sampling varies between runs. A 9-point gap can appear by chance on 12 items. Use `--repeat` and compare across runs before you trust the number.

4. Trigger at a fixed token threshold well below the window, for example 50% to 60%, checked before every call. Copy word for word: the refund limit rule, every other policy constraint, and the last few turns. Summarise: earlier conversation, into decisions, constraints and open items. Drop: full tool results, replaced by pointers such as an order id you can fetch again. Justification: ConstraintRot measured 0% violations when the constraint survived compaction and 38% when it was dropped, and its Compaction-Eviction Attack shows in-context content can push the summariser to drop a policy on purpose. So the refund rule must never depend on a summariser's choice. Cost records: the summarising call is a second billed call, so add it to the same run record. Anthropic's compaction feature leaves those tokens out of top-level usage, so a meter that reads only `input_tokens`/`output_tokens` counts too little; sum `usage.iterations` instead.

5. The 2026 study of 10,664 trajectories found that task success falls with the number of steps, not with context length. A smaller context window made the fall steeper, with a logit slope of -0.69 against -0.44. So the win may come from lower cost or from chance, not from fixing the decline. To separate the explanations, run two tests. Hold the step count fixed and vary the context length. Then hold the context length fixed and vary the step count. Measure task success in each. If success follows the step count in both tests, compaction was not the cause.

</details>

---

## Things I could not verify

These claims sit in the lesson because the course phase asserts them. The study run behind this version, on 2026-09-19/20, could not re-open the source. Treat each as quoted from the phase's own 2026-09-17 check, not as confirmed today.

- Sarathi-Serve numbers from its section 5: "up to 6.3x for LLaMA2-70B on eight A40s, against Orca", the ~25% overhead at a 512-token budget on Yi-34B (§5.4.1, Figure 14), and the budget guidance of 512 for a strict latency target and 2,048 for a relaxed one (§4.3). That section lies past the truncation of both HTML renderings the study run fetched. The abstract's 2.6x/3.7x/5.6x capacity figures are verified. Those are the ones section 2.4 teaches.
- The Format Tax body numbers: the 3.9/1.6 point split, the 36-of-39 cell counts, the per-model deltas, 55.7%→92.2% validity, and the +6.8/+9.2 mitigation gains. The abstract is verified. It supports the headline: the prompt, not the decoder, is the dominant cost.
- OpenAI's error-codes page omitting `context_length_exceeded`. Also Anthropic's context-overflow error shape: 400 `invalid_request_error`, "prompt is too long", no code. The phase checked both pages on 2026-09-17. This run did not re-open them.
- The .txt rebuttal's parser numbers: 0.35 with a strict regex parser, 0.61 with a flexible one. The blog was not re-fetched.
- Claude Code compacting "at about 967,000 tokens" on 1M-window models. No source was opened for this number. Section 2.6 carries only the verified Anthropic defaults: 100,000 for tool-result clearing, 150,000 for server-side compaction.
- Lost in the Middle's exact figures: 75.8% for first position and 53.8% for middle position. These are readings of Figure 5. The prose is verified: the drop exceeds 20%, and mid-context accuracy falls below the 56.1% closed-book score.
- All `batching_sim.py`, `structured_lab.py` and `compactor.py` outputs. This run cannot execute code. The phase's 2026-09-17 re-runs are the only evidence.
- vLLM's structured-outputs backend `auto` fallback order, and SGLang 0.5.19's XGrammar default. The phase defers these to Phase 4A section 4.2. They were not re-checked at the v0.29.0 tag this run.
- The numbers from Chroma's context-rot study, Self-Compacting Agents, Slipstream, TRACE, "How Fast Do Agents Rot?" and the Tam et al. tables. None were re-opened this run. The phase's 2026-09-17 checks stand.

## Cheatsheet — part B

```
CHUNKED PREFILL
  no chunking : one big prefill freezes every stream in the batch
  chunking    : prefill shares max_num_batched_tokens with the decodes
                decodes are reserved first: 2048 - 3 decodes = 2045 prefill
  smaller budget → better inter-token smoothness, worse TTFT
  larger budget  → better TTFT, worse smoothness
  measured (batching_sim, chunked row): budget 512 → gap 35ms, TTFT 1094ms
                                        budget 2048 → gap 81ms, TTFT 925ms
                                        budget 8192 → gap 265ms, TTFT 908ms
  48k prompt: chunking +112ms mean TTFT, worst gap 1460ms → 81ms
  vLLM 0.29.0 max_num_batched_tokens (get_batch_defaults, vllm/engine/arg_utils.py):
    API server   : 16384 (B200/B300) / 8192 (H100,H200) / 2048 (rest, incl A100)
    offline LLM  : 16384 (H100 and up) / 8192 (rest); A100 excluded by name (PR #17885)
    performance_mode=throughput doubles unset defaults
  stream_interval (default 1) batches tokens before sending: a UNIFORM gap
    pattern is this knob, not a prefill stall
  queue full (max_num_queued_reqs/tokens) → HTTP 503, not a provider outage
  measure MAX INTER-TOKEN GAP; TTFT and total latency cannot see a freeze

CONSTRAINED DECODING
  mask illegal tokens each step → shape guaranteed on hosted strict APIs;
    engine-dependent self-hosted (XGrammar: 38 under-constrained test-suite
    categories vs Guidance 1), stopping NEVER guaranteed
  prompt only → no guarantee | json_object → valid JSON
  json_schema + strict → schema obeyed (see asterisk above)
  finish_reason still required: a truncated answer is a parse failure
  compile medians (JSONSchemaBench): Guidance 0.01s, XGrammar 0.11–0.30s,
    Outlines 3.48–8.05s, and 40s–10min on minItems/maxItems/enum/Array
  OpenAI: first request with ANY schema pays the compile, on EVERY model
  schema rules: every key in required, additionalProperties false,
    optional = union with null; root is an object; ≤5000 props, ≤10 levels,
    ≤120k chars of names/enum/const, ≤1000 enum values
  THE TAX: dominant cost is the prompt asking for the format, not the decoder
    (body numbers: ≈ -3.9 pts prompt vs ≈ -1.6 pts decoder, quoted from phase)
  constrained decoding can be FASTER per token (batch-1 evidence) and can
    beat unconstrained when the reasoning field comes FIRST
  fixes: reasoning field first; two calls; thinking. Measure with YOUR parser

CONTEXT BUDGET AND COMPACTION
  zones with caps + headroom for the reply AND for the summarising call
  TRIGGER on a token threshold you chose, before the call
    compactor.py: 0.60 x 32,000 = 19,200 → fires at turn 25
    shipped: context editing 100k (keep 3 tool uses), compaction API 150k (min 50k)
  COPY WORD FOR WORD: constraints. 0% violations when kept, 38% when dropped,
    30% avg after compaction, and injection can force the drop (Governance Decay)
  SUMMARISE: decisions, open items.   DROP: tool results, keep pointers
  BACKSTOP: HTTP 400 + code context_length_exceeded → compact → retry ONCE
    check order: status, code, type, text. Never resend the same prompt unchanged
  Anthropic on-demand compaction: compaction:{type:"summarize"} → signed block,
    send FIRST each later request; misplaced → 400 compaction_block_misplaced;
    pause_after_compaction hands you the insertion point
  tool-result clearing invalidates cached prefixes; web-search tools inflate
    cache_read_input_tokens and can fire the trigger EARLY
  compaction is billed: sum usage.iterations, not just input/output_tokens
  400k-token prompt x 50 steps x $2.00/M (gpt-4.1) = $40 per conversation

THE COMMANDS (all offline except the live structured_lab runs)
  batching_sim.py --token-budget N          structured_lab.py --self-test
  compactor.py --simulate --turns 40        compactor.py ... --no-compaction
  compactor.py --simulate --turns 12 --inject-overflow 5
```

## Two things you could post

- **"Your LLM dashboard is green and your stream is freezing."** Claim: TTFT and total latency cannot see a mid-answer freeze. The metric is max inter-token gap, and one config value decides how bad it gets. What makes it his: he runs `batching_sim.py` himself. He can show his own 764ms→81ms table, then time-stamp a real hosted stream the same week.
- **"Strict JSON mode changed my model's accuracy, and the internet argued about the wrong cause."** Claim: the quality drop from structured output comes mostly from the prompt asking for the format, not from the decoder enforcing it. And the reasoning field must come first. What makes it his: E8–E10 give him his own tax numbers, on his own tickets, with his own parser. That is exactly the reporting discipline the research keeps failing at.

## Sources

Every link below was fetched and checked on 2026-09-12 by the course author. Four pages were fetched again on 2026-09-17 and returned 200: the vLLM tuning guide, Let Me Speak Freely, The Format Tax, and the OpenAI guide. The study run for this version re-opened several sources on 2026-09-19/20: the Sarathi-Serve paper, the vLLM v0.29.0 source files, the OpenAI guide in full, both Anthropic docs pages, JSONSchemaBench, the XGrammar blog, the Format Tax and Governance Decay abstracts, Lost in the Middle, and the Claude Code issue.

**Read before the lab**

- **Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve, Agrawal et al., OSDI 2024** — https://arxiv.org/abs/2403.02310 · readable version: https://ar5iv.labs.arxiv.org/html/2403.02310. Why: the source of section 2.4. Focus: section 3 for why a long prefill raises inter-token latency, section 4 for chunked prefills and the token budget, Figure 9 for the up-to-28.3x TBT rise. When: before the lab.
- **vLLM v0.29.0 source: scheduler.py and arg_utils.py** — https://raw.githubusercontent.com/vllm-project/vllm/v0.29.0/vllm/config/scheduler.py and https://raw.githubusercontent.com/vllm-project/vllm/v0.29.0/vllm/engine/arg_utils.py. Why: the primary source for every default quoted in section 2.4, including `get_batch_defaults()`, `stream_interval` and the 503 queue valve. When: before you self-host in Phase 4A.
- **vLLM optimization and tuning guide, official documentation** — https://docs.vllm.ai/en/latest/configuration/optimization.html. Why: smaller `max_num_batched_tokens` values such as 2048 "achieve better ITL because there are fewer prefills slowing down decodes"; higher values "achieve better time to first token". When: when you tune.
- **Efficient Guided Generation for Large Language Models, Willard and Louf, the Outlines paper** — https://arxiv.org/abs/2307.09702. Why: the mask mechanism in section 2.5. Focus: section 2.2 for the mask formula, section 3 for the index that maps each state to its legal tokens. Do not quote a speedup from section 3.2; the authors hedge it themselves. When: after the lab.

**Constrained decoding**

- **JSONSchemaBench** — https://arxiv.org/abs/2501.10868 · readable version: https://ar5iv.labs.arxiv.org/html/2501.10868. Why: the compile times (Tables 2 and 3), the under-constrained failure counts (Table 6), the batch-1 speedup (Table 2) and the reasoning-first accuracy table (Table 8) in section 2.5. When: after E8.
- **The Format Tax, Lee, D'Antoni, Berg-Kirkpatrick, April 2026** — https://arxiv.org/abs/2604.03616. Why: settles the constraint-tax debate by separating prompt cost from decoder cost. Focus: section 4.2 for the split, 4.3 with Table 5 for the two fixes. A preprint with no peer-review venue found; weigh accordingly. When: after E9.
- **Let Me Speak Freely?, Tam et al., EMNLP 2024 Industry Track** — https://arxiv.org/abs/2408.02442. Why: the original tax claim. Focus: Tables 1, 7 and 8 (Table 8 shows constraints helping classification), and the words "is assumed" in section 2, which the rebuttals attack. When: before The Format Tax.
- **Say What You Mean: A Response to "Let Me Speak Freely", .txt, the Outlines authors** — https://blog.dottxt.ai/say-what-you-mean.html. Why: the parser-moves-the-score demonstration. When: with the paper above.
- **XGrammar blog and paper, MLC** — https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar. Why: the adaptive token mask cache: more than 99% of tokens usually context-independent, up to 3.5x faster mask generation on JSON schema. When: after the lab.
- **XGrammar-2, MLC** — https://blog.mlc.ai/2026/05/04/xgrammar-2-fast-customizable-structured-generation. Why: Structural Tag, a current approach to the constraint tax: free text until a trigger token turns on the constrained region. No accuracy measurement published yet. When: when you want the frontier.
- **OpenAI Structured Outputs guide, official documentation** — https://developers.openai.com/api/docs/guides/structured-outputs. Why: the "Supported schemas" section: keyword support, the size limits, key ordering, and the first-request latency note that now applies to every model. When: before you design a schema, and re-read it periodically.

**Context management**

- **Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents, June 2026** — https://arxiv.org/abs/2606.22528. Why: the ConstraintRot numbers and the Compaction-Eviction Attack in section 2.6; the reason the `constraints` list exists in `compactor.py`. When: before you write a compactor.
- **Anthropic compaction and context editing reference** — https://platform.claude.com/docs/en/build-with-claude/compaction and https://platform.claude.com/docs/en/build-with-claude/context-editing. Why: the verified default triggers, on-demand compaction, `pause_after_compaction`, `applied_edits`, the billing caveat (`usage.iterations`) and the premature-compaction failure mode. When: before you build the trigger.
- **Claude Code issue #24460: project instructions lost after /compact** — https://github.com/anthropics/claude-code/issues/24460. Why: the production failure that mirrors ConstraintRot in the wild, closed as not planned with a user-side workaround. When: alongside Governance Decay.
- **Effective context engineering for AI agents, Anthropic, 29 September 2025** — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents. Why: what to keep: architectural decisions, unresolved bugs, implementation details. It gives no numeric threshold; do not credit one to it. When: after the lab.
- **Context Rot: How Increasing Input Tokens Impacts LLM Performance, Chroma Research, 14 July 2025** — https://www.trychroma.com/research/context-rot. Why: the LongMemEval comparison of a ~300-token focused input with a ~113,000-token full input, across 18 models. The often-repeated "30% drop" figure does not appear on the page; do not quote it. When: after the lab.
- **Lost in the Middle: How Language Models Use Long Contexts, Liu et al., TACL 2024** — https://arxiv.org/abs/2307.03172 · readable version: https://ar5iv.labs.arxiv.org/html/2307.03172. Why: the position curve section 2.6 quotes, and the finding that extended-context models were not better at using their input. Focus: Figure 5. When: after the lab.
- **Slipstream: Trajectory-Grounded Compaction Validation for Long-Horizon Agents, May 2026** — https://arxiv.org/abs/2605.08580. Why: the validation gap and the two results quoted in section 2.6. When: when your compactor is wrong often enough to matter.
- **TRACE: Toward Reliable Context Compression for Long-Horizon Agents, August 2026** — https://arxiv.org/abs/2608.06503. Why: blocked and repeated actions after a compaction boundary. When: with Slipstream.
- **Self-Compacting Language Model Agents, June 2026** — https://arxiv.org/abs/2606.23525. Why: the rubric that decides when to compact; the counter-argument to token thresholds. When: when a fixed threshold fires at bad moments.
- **How Fast Do Agents Rot?, August 2026** — https://arxiv.org/abs/2609.01660. Why: success falls with step count, not context length (logit slopes -0.69 vs -0.44), across 10,664 trajectories and nine models. When: before checkpoint question 5.
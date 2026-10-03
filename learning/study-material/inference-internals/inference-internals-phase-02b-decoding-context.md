# Phase 2B — Decoding and context (the stream freeze, the schema, and the 400)

Part A showed how the server shares one GPU between many requests. Part B covers three problems that you see from the client side. A stream can freeze in the middle of a sentence. A strict JSON schema can change answer quality. A long agent run can fail with a 400 error.

Part A is a prerequisite. Section 2.4 builds on the scheduler loop and the token budget from section 2.1. Section 2.6 orders the prompt zones with the prefix rule from section 2.3. This part does not explain those ideas again.

This part pays two debts from Phase 1:

- Phase 1 exercise E7 overflowed the context window on purpose and got a 400 back. Section 2.6 builds the compaction trigger that prevents it.
- Phase 1 exercise E11 truncated a JSON answer and said that constrained decoding exists. Section 2.5 teaches constrained decoding and measures its cost.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  2.4  Chunked prefill           — the trade between TTFT and TPOT,       │
│                                   and the stream freeze                  │
│  2.5  Constrained decoding      — token masking, and the constraint tax  │
│  2.6  Context budget and        — the trigger that prevents Phase 1 E7,  │
│       compaction                  and the backstop that catches it       │
└──────────────────────────────────────────────────────────────────────────┘
```

Time: 1.5 to 2 hours. Three commands in this part need no API key and no GPU: `batching_sim.py`, `structured_lab.py --self-test`, and `compactor.py --simulate`. The live `structured_lab.py` runs need `export OPENAI_API_KEY=sk-...`. You can also use any OpenAI-compatible endpoint through `--base-url` and `--key-env`.

Setup: use the same `code` directory and install step as part A.

---

## 2.4 — Chunked prefill (the trade between TTFT and TPOT)

Why this matters: section 2.1 left one number without an explanation. Continuous batching produced a 764ms worst gap between two tokens of one answer. Your user sees that gap as a frozen stream. This section explains the cause and the fix.

Go back to the scheduler loop. One iteration runs one forward pass. That pass can do prefill work, decode work, or both. Now a new request arrives with a 24,000-token prompt.

Without chunking, the server has two bad choices:

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

The durations come from the simulator's cost model in `batching_sim.py:49`, which part A section 2.1 shows. Three decodes cost 18 + 0.12 × 3 = 18.4ms. A 24,000-token prefill costs 24,000 × 0.03 = 720ms. A 2,045-token slice plus three decodes costs 61.35 + 18.36 = 79.7ms. The prompt needs 24,000 / 2,045 = 11.7 slices, so 12 iterations.

The budget is shared. With `max_num_batched_tokens=2048` and 3 decoding requests, the iteration spends 3 tokens on decode. It spends up to 2,045 on prefill. The simulator reserves the decode tokens first. `batching_sim.py:122` computes `room = max(token_budget - len(decoding) - prefill_tokens, 0)`. Without chunking, `batching_sim.py:128` sets `decoding = []`, so no decode runs in that pass.

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

Chunked prefill adds 3,140 - 3,028 = 112ms to mean TTFT. In return, the worst gap between two tokens falls from 1,460ms to 81ms. That is 18x smaller, and it is the number your users feel during a stream.

The Sarathi-Serve paper measured this effect on real hardware. It mixed a prefill into a decode batch without chunking. Time between tokens rose 28.3x compared with a decode-only batch. That is the freeze, measured on GPUs rather than simulated.

Chunking also has a cost, and the same paper measures it. At a 512-token budget, it found about 25% overhead on Yi-34B. Splitting a prefill repeats work at the chunk boundaries. So the setting has a lower limit. Below that limit, you pay for smoothness with throughput.

This is a real trade. The right direction depends on your product:

```
┌──────────────────────────┬─────────────────────────┬───────────────────────┐
│                          │ larger token budget     │ smaller token budget  │
├──────────────────────────┼─────────────────────────┼───────────────────────┤
│ TTFT for long prompts    │ better                  │ worse                 │
│ inter-token smoothness   │ worse                   │ better                │
│ good for                 │ batch jobs, summarising │ chat, voice, streaming│
│ vLLM setting             │ max_num_batched_tokens  │ same setting, lower   │
└──────────────────────────┴─────────────────────────┴───────────────────────┘
```

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

Carry one correction into Phase 4. `max_num_batched_tokens` has no single default in vLLM 0.29.0. The server picks it at startup. The choice depends on the GPU class. It also depends on whether you run the offline `LLM` class or the API server. On an H100 through the API server, the value is 8,192. On most other GPUs, including the A100, it is 2,048. The constant `DEFAULT_MAX_NUM_BATCHED_TOKENS` exists only for tests. This was checked against the v0.29.0 source tree on 2026-09-12.

**What this means on a hosted API.** You cannot set `max_num_batched_tokens` on another company's server. You still see the effect, and you can act on it in two ways:

1. Record inter-token gaps, not only TTFT and total time. An average does not show a frozen stream.
2. Keep your own prompts smaller. Your large prefill freezes other users' streams. On a single-tenant deployment, it freezes your own.

**The sentence to remember:** prefill and decode share the same forward pass. A long prompt either waits or freezes the other streams. Chunking decides which.

**The trap:** teams measure TTFT and total latency and call the stream healthy. Neither number shows an 800ms freeze in the middle of an answer. Add a maximum inter-token gap metric before you promise a streaming experience.

**Try this now:** run `python phase02_internals/batching_sim.py --token-budget 512` and then `--token-budget 8192`. In the `chunked` row, mean TTFT and worst gap move in opposite directions. Expect 1,094ms and 35ms at 512, and 908ms and 265ms at 8,192.

---

## 2.5 — Constrained decoding and the constraint tax

Why this matters: in Phase 1 exercise E11, a truncated JSON answer broke your parser. The lesson there was `finish_reason`. This section covers the other half. A prompt that asks for JSON is a request, not a guarantee. Constrained decoding makes it a guarantee. It also has a cost, and most teams never measure it.

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
  │ "["     2.9  │    │ illegal here  ✗  │   →    │ "["     -inf │
  └──────────────┘    └──────────────────┘        └──────────────┘

  The state machine now moves to "expecting a key or }". The next step gets a
  different mask. Prose can never appear, because prose tokens are never legal.
```

The mask comes from a state machine. The engine builds it from your schema in three steps:

1. It reads your JSON Schema or grammar.
2. It builds the states.
3. For each state, it computes which vocabulary tokens are legal.

Three libraries do this work today: Outlines, XGrammar, and llguidance. vLLM and SGLang use them inside.

Building the state machine takes time, and the time depends on the library. JSONSchemaBench measured median grammar compilation time on the same schemas:

- Guidance: about 0.01s.
- XGrammar: 0.11s to 0.30s.
- Outlines: clearly higher. It converts the JSON Schema into a regular expression first.

XGrammar runs its compilation at the same time as the prefill, so you often do not see the delay.

On hosted APIs this changed recently, and some older material is now wrong. OpenAI's current structured outputs page says the first-request schema delay applies to fine-tuned models. The page states: "Other models do not have this limitation." The page gives no time limit in either case. So measure your own provider. Quote checked on 2026-09-17.

### The three levels, and what each one promises

```
┌────────────────────┬───────────────────┬──────────────────┬─────────────────┐
│                    │ prompt only       │ json_object      │ json_schema     │
│                    │                   │                  │ strict: true    │
├────────────────────┼───────────────────┼──────────────────┼─────────────────┤
│ valid JSON         │ not guaranteed    │ guaranteed       │ guaranteed      │
│ correct keys       │ not guaranteed    │ NOT guaranteed   │ guaranteed      │
│ values within enum │ not guaranteed    │ not guaranteed   │ guaranteed      │
│ prose wrapping     │ happens           │ cannot happen    │ cannot happen   │
│ first-call cost    │ normal            │ normal           │ engine compiles │
│                    │                   │                  │ the grammar     │
│ can still truncate │ yes               │ yes              │ yes             │
└────────────────────┴───────────────────┴──────────────────┴─────────────────┘
```

Read the last row twice. A schema controls which tokens are legal. It does not control when generation stops. Suppose `max_tokens` runs out in the middle of an object. You get a truncated document. It still follows the schema's shape, and it still cannot be parsed. Only `finish_reason` tells you this happened. Phase 1 E11 is that failure, and strict mode does not remove it.

### The constraint tax

Forcing a schema can change the quality of the answer, not only its shape. Researchers disagreed about this for two years. A 2026 paper explains the disagreement.

**The original claim.** A 2024 EMNLP paper, "Let Me Speak Freely?", reported large drops on reasoning tasks:

- On GSM8K, claude-3-haiku scored 86.99 in plain JSON mode. It scored 23.44 with a schema constraint.
- gpt-3.5-turbo fell from 74.70 to 49.25.

Two details matter. First, the standard deviations were very large: 22.9 and 12.0 across 9 prompts. Second, the paper's own appendix shows constraints helping classification tasks. On DDXPlus, gemini went from 41.6 to 60.3. claude-3-haiku went from 33.8 to 52.0.

**The rebuttal.** The authors of Outlines ran the same model and tasks again. They measured the opposite:

- GSM8K: 0.77 unstructured and 0.78 structured.
- Last Letter: 0.73 and 0.77.

They also raised an objection. The original paper never confirmed that a provider's JSON mode uses grammar-constrained decoding. The paper says only that it "is assumed". A third benchmark, JSONSchemaBench, also measured small gains.

**The 2026 answer.** A paper called "The Format Tax" tested 6 open-weight and 4 closed-weight models. It used 4 formats and 4 tasks. It separated the two possible causes of the drop:

- Asking for a format in the prompt cost 3.9 points on average.
- Adding grammar-constrained decoding on top cost 1.6 points on average.
- 39 result cells had a statistically significant effect. In 36 of them, the effect was already present from the prompt alone. Only 3 cells showed a drop from constrained decoding alone.

So the tax is real. The decoder causes the smaller part of it.

```
WHERE THE FORMAT TAX COMES FROM (The Format Tax, average points lost)

  format request in the prompt    ████████████████████████████████████████  3.9
  constrained decoding on top     ████████████████                          1.6
```

Two more results from the same paper are useful to you:

- Three newer closed-weight models showed changes near zero or above zero without constrained decoding. They were claude-haiku-4.5, grok-4.1-fast, and gpt-5.4-nano. claude-haiku-4.5 scored +1.2 and grok-4.1-fast scored +2.5 against their own free-form baseline. The older gpt-5-nano still lost 5.2 points without constrained decoding and 8.0 points with it. Small open models lost 5 to 9 points. So any claim that "structured output costs X percent" is wrong unless it names the model.
- Constrained decoding raised format validity from 55.7% to 92.2%. Accuracy moved from 57.3% to 55.7%. The free-form baseline was 61.5%. The paper's summary: "higher compliance does not translate into better reasoning". Quote checked on 2026-09-17.

**The scoring warning.** Every group in this debate hit the same problem: the parser changes the score.

- Tam et al. used a model to parse answers. Their own table shows the parser choice moving a score by up to 42 points.
- The Format Tax authors switched from a rule-based extractor to a model judge. Their average MATH-500 tax fell from 10.1 points to 6.6 points. So about a third of the measured tax came from scoring.

When you measure your own tax, fix the parser first and report it with the result. A number without its parser tells you nothing.

So measure it. `structured_lab.py` sends the same 12 labeled tickets through all three modes:

```bash
python phase02_internals/structured_lab.py --self-test     # no key needed
export OPENAI_API_KEY=sk-...
python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap
```

The script reports six values per mode: accuracy, parse failures, output tokens, mean latency, first-call latency, and cost. The accuracy gap between `prompt` and `strict` is your constraint tax on this task. The gap can be negative. A negative gap means the schema helped.

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

The property order is the point. OpenAI's structured outputs page states that outputs follow the key order of the schema. If `reasoning` comes last, it changes nothing, because the answer is already chosen. This schema rule has a mechanical reason and direct evidence:

- Tam et al. found that 100% of gpt-3.5-turbo JSON-mode answers put the answer key before the reason key. That turns step-by-step reasoning into a direct answer.
- JSONSchemaBench used the opposite order. It measured constrained decoding matching or beating unconstrained decoding on the same three tasks.

The Format Tax also measured two other fixes:

```
┌────────────────────────────┬──────────────┬───────────────┬────────────────┐
│ mitigation                 │ improved     │ made worse    │ average gain   │
├────────────────────────────┼──────────────┼───────────────┼────────────────┤
│ two calls: answer freely,  │ 42 of 72     │ 2 of 72 (3%)  │ +6.8 points    │
│ then reformat              │              │               │                │
│ thinking enabled before    │ 43 of 72     │ 11 of 72 (15%)│ +9.2 points    │
│ the structured answer      │              │               │                │
└────────────────────────────┴──────────────┴───────────────┴────────────────┘
```

Two calls is the safer choice. It costs one extra request. Thinking gives a larger gain on maths and does not help on writing. Neither fix is free. Measure before you pick one.

**Three schema rules to get right on day one.**

1. Every property must appear in `required`.
2. `additionalProperties` must be `false`.
3. To make a field optional, use a union with null, such as `"type": ["string", "null"]`. Do not leave the key out of `required`.

The list of unsupported JSON Schema keywords has become shorter. Check the current page, not an older blog post. As of September 2026, OpenAI's page lists some keywords as supported for normal models only. They are `pattern`, `format`, `multipleOf`, `minimum`, `maximum`, `minItems`, and `maxItems`. Fine-tuned models do not support them yet. These keywords are unsupported for all models: `allOf`, `not`, `dependentRequired`, `dependentSchemas`, `if`, `then`, `else`. Some other keywords do not appear on the page, so their status is not documented. Test such a keyword before you depend on it.

**When you serve the model yourself, the engine picks a backend.** Phase 4A section 4.2 covers this. The behaviour matters now because it changes both errors and latency:

- vLLM 0.29.0 defaults to `auto`. It checks your schema against XGrammar first. If a keyword is unsupported, it falls back to Guidance, then to Outlines.
- If you pin one backend instead, the same unsupported keyword becomes an error.
- SGLang 0.5.19 defaults to XGrammar. It has no per-schema fallback.

The compile times quoted above differ by an order of magnitude between these backends. So a silent backend switch is also a latency change.

**The sentence to remember:** constrained decoding masks illegal tokens at every step. The shape is guaranteed. The stopping point is not. The effect on quality is yours to measure.

**The trap:** an older article may tell you that every new schema costs a compile on the first request. You then design around a cost that your provider may no longer charge. Measure it. Still define schemas once, at import time. A self-hosted engine does pay that cost for each distinct schema.

**Try this now:** run `python phase02_internals/structured_lab.py --model gpt-4.1-mini --modes strict --repeat 3`. Compare the `first call` column with the `mean lat` column. A large gap means your provider compiles each new schema. A gap near zero matches OpenAI's current documentation for models that are not fine-tuned. Record which result you got, with the date.

---

## 2.6 — The context budget and the compaction trigger

Why this matters: Phase 1 exercise E7 sent a prompt that was too large and got a 400 back. That exercise promised the fix in this section. The fix is more than a try and except block.

The context window is the maximum number of tokens the model accepts in one call. Compaction replaces old conversation turns with a shorter summary, so the prompt fits again.

### First, why a bigger window does not solve this

You might think a one million token window ends the problem. It does not. There are three separate reasons, and each one has evidence.

**Reason 1: accuracy falls as input grows.** Chroma's context rot study tested 18 models. They came from the Claude, GPT, Gemini, and Qwen families. It ran simple retrieval tasks at many input lengths. Performance fell as length grew, in every family. The study also ran a LongMemEval test. Every model scored higher on a focused input of about 300 tokens. The full input had about 113,000 tokens and contained the same answer.

**Reason 2: position inside the window matters.** The Lost in the Middle study moved the needed document to different positions. It measured accuracy at each position. With 20 documents, GPT-3.5-Turbo scored 75.8% when the answer was first. It scored 53.8% when the answer was in the middle. With no documents at all, it scored 56.1%. So the middle score was lower than the score with no documents. The models are from 2023. Treat the numbers as the shape of the effect, not as current values.

**Reason 3: a full large window is expensive.** Cost grows with every input token. A 400,000-token prompt on every step of a 50-step loop is 20 million input tokens. The `deep` role in `prices.yaml` is gpt-4.1 at $2.00 per million input tokens. So one conversation costs 20 × $2.00 = $40.

So a larger prompt costs more for every extra token, and each extra token helps less.

### The budget: zones with caps

A context window has a fixed size, and several sources write into it. Without caps, the largest source takes the space. The largest source is usually a tool that returned a large result. So split the window into zones, and give each zone a cap.

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

People forget the last row most often. If you fill the window to the limit, the summarising call cannot run either. That call is the one that would fix the problem.

### The trigger: compact early, at a threshold you chose

Do not wait for the error. Count the tokens before every call. Compact when the total passes a threshold that you set.

Shipped products set thresholds well below the window:

- Anthropic's context editing tool clears old tool results at a default trigger of 100,000 input tokens. It keeps the last 3 tool uses.
- Anthropic's server-side compaction feature defaults to a trigger of 150,000 input tokens. It rejects values below 50,000.
- Claude Code compacts at about 967,000 tokens on models with a one million token window. On other models it compacts at the 200,000 limit.

All three use the same pattern: a fixed number, chosen in advance, below the limit.

A newer idea is worth knowing. The Self-Compacting Language Model Agents paper argues that a token threshold can fire at a bad moment. For example, it can fire in the middle of a derivation. The paper lets the model decide instead, with a rubric. Compact when a sub-task ends. Never compact mid-derivation or while stuck. Reported results:

- Up to 18.1 points higher on math benchmarks.
- 5 to 9 points higher on agentic search.
- 30 to 70 percent lower cost per question.

Treat this as a likely future direction. Start with a threshold, because a threshold is simple and you can test it.

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

The trigger is at 32,000 × 0.60 = 19,200 tokens. Turn 25 is the first turn above it. Note one detail of the output. The script counts every history message as one "turn". Each loop turn adds a user message and an assistant reply. So at loop turn 25, the history holds 24 × 2 + 1 = 49 messages. 45 are summarised, and 4 are kept.

### What to keep, and the number that shows why

A summary keeps what the summariser found interesting. That is where it fails. A later turn cannot recreate three kinds of facts: decisions, constraints, and open items.

Constraints are the most dangerous to lose. The "Governance Decay" paper shows why. It built a benchmark called ConstraintRot and ran 1,323 episodes across seven model families. Each episode stated policy constraints in the context. A program graded the tool calls, not a model. The results:

- With the policy fully visible, the violation rate was 0%.
- After compaction, it rose to 30%, and reached 59% for some models.
- When the constraint survived the summary, violations stayed at 0%. When the summary dropped it, violations were 38%.
- The paper's fix, Constraint Pinning, keeps constraints out of the lossy summary. It brought violations back to 0%.

Treat that as an engineering rule. Do not let a language model decide whether your safety rule is worth keeping. Copy constraints across the compaction boundary as literal text.

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

### The backstop: catch the 400, compact, retry once

The trigger can still be wrong. A tool can return far more than you expected. So keep a second layer, and make it log loudly.

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

Detect the error by its machine-readable fields, not by its wording. The stable parts are:

- HTTP status 400.
- An error `type` of `invalid_request_error`.
- An error `code` of `context_length_exceeded`.

OpenAI's public error-codes page does not list this error at all. So any exact message text you hardcode today can change without notice. `is_context_overflow` at `compactor.py:227` shows the order of checks. It checks the status first, then the code, then the error type, and the message text last. A 429 or a 5xx is never an overflow, even when its text looks like one. Anthropic sends no error code. Its context-windows page says an oversized input returns a 400 `invalid_request_error` with the text "prompt is too long". Checked on 2026-09-17. The function matches that by type and text.

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

Compaction is not a solved problem. Be careful with any source that says it is.

- **Compaction can lower accuracy.** The Slipstream paper describes a validation gap. The compactor must shorten the context without knowing what the agent will need later. The paper validates candidate summaries outside the main request path. It reports up to 8.8 percentage points of accuracy recovered, and up to 39.7% lower end-to-end latency.
- **Repeated compaction makes runs less stable.** TRACE, an August 2026 study from the University of Virginia and Nokia, used the AppWorld benchmark. It found that compression weakens the effect of recent turns. The agent then hits more blocked actions and repeats more work. Results also vary more between runs.
- **Long tasks fail for reasons beyond token count.** A study of 10,664 trajectories across nine models measured this. Task success fell with the number of steps, not with the context length. A smaller context window made success fall faster, not slower. Reliability per step rises with model size, but it stays below 1. So a long enough task fails anyway.
- **Compaction is billed.** Anthropic's compaction feature runs as a separate sampling iteration. Its tokens are not included in the top-level usage counts. You must add up `usage.iterations` to see the real total. Your own summarising call has the same property. It is a second call, and your cost meter must count it.

**The sentence to remember:** compact at a threshold you chose. Copy constraints across the boundary as literal text. Treat a 400 as a bug in your trigger, not as a normal event.

**The trap:** anything a summary drops is gone for good. When the summary drops a policy constraint, measured violations jump from 0% to 38%. Decide what to copy word for word before you decide what to summarise.

**Try this now:** run `python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5` and read the backstop lines. Then open `compactor.py:670`. Confirm that `cm.compact` changes the input before the retry on line 671.

---

## 🧪 Hands-on lab — part B

Setup: `cd ~/Desktop/project/code/study-material/inference-internals/code && pip install -e .`

Three of these six exercises need no API key and no GPU. They are marked "offline". The rest need `export OPENAI_API_KEY=sk-...` or another OpenAI-compatible endpoint through `--base-url` and `--key-env`.

**Run status:** every offline command below was run on 2026-09-17, and the output matched the numbers printed here. The API-calling commands were not run against OpenAI, because no API key was available on this machine on 2026-09-12. The command flags were checked against the shipped scripts. So E8, E9, and E10 are marked UNVERIFIED against a live provider. Run them and record what you see.

**Exercise numbers:** part B holds E4 and E8 to E12. The numbers are the same as in the original single Phase 2 document, because other phases cite them. **E1**, **E2**, **E3**, **E5**, **E6**, and **E7** are in part A.

Record every number. Phase 5B uses your gap measurements.

- [ ] **E4 (offline).** Find the token budget trade.
  - Run: `python phase02_internals/batching_sim.py --token-budget 512` then `python phase02_internals/batching_sim.py --token-budget 8192`.
  - Expected, in the `chunked` row: mean TTFT 1,094ms and worst gap 35ms at 512. Mean TTFT 908ms and worst gap 265ms at 8,192. The two numbers move in opposite directions.
  - Then read the limit of the model. The simulator does not model chunking overhead. Sarathi-Serve measured about 25% overhead at a 512-token budget on Yi-34B. A very small budget has a real throughput cost.
  - Teaches: `max_num_batched_tokens` is a product decision. Chat and batch jobs want opposite settings.

- [ ] **E8 (live, UNVERIFIED against a live provider).** Measure the constraint tax on a real task.
  - Run offline first: `python phase02_internals/structured_lab.py --self-test`. Confirm that all six parser cases pass and the last line is "all self-tests passed".
  - Then run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap`
  - Expected: `prompt` mode records at least one parse failure across 12 tickets. `json` and `strict` record zero. The accuracy column shows your tax. The tax can be positive or negative.
  - Costs at most: about $0.02 for all three modes.
  - Teaches: the shape guarantee and the quality question are two different things.

- [ ] **E9 (live, UNVERIFIED against a live provider).** Test the reasoning field.
  - Run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --reasoning-field`
  - Expected: output tokens, cost, and latency rise. Accuracy may or may not rise. Compare with E8, and decide whether the trade is worth it on this task.
  - Teaches: a free-text field before the constrained fields is a change you can measure.

- [ ] **E10 (break-it, UNVERIFIED against a live provider).** Truncate an answer that follows the schema.
  - Run: `python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --modes strict --reasoning-field --max-tokens 15`
  - Expected: the `truncated` column fills up. Parse failures appear, even though every answer followed the schema until it stopped.
  - Teaches: a strict schema guarantees legal tokens, never a complete answer. `finish_reason` is still required, as Phase 1 E11 said.

- [ ] **E11 (offline).** Watch the compaction trigger fire.
  - Run: `python phase02_internals/compactor.py --simulate --turns 40`
  - Expected: the prompt grows to 19,409 tokens and the trigger fires at turn 25. The prompt drops to 2,270 tokens. The script reports 45 turns summarised and 4 kept verbatim.
  - Then run it with `--trigger-ratio 0.3`. Expected: the trigger moves to 9,600 tokens and fires three times, at turns 13, 23, and 33.
  - Then run it with `--keep-last 10`. Expected: one compaction at turn 25, down to 4,604 tokens, with 10 kept verbatim.
  - Teaches: the trigger is a number you choose. The token counts show the effect of that choice.

- [ ] **E12 (break-it, offline).** Reproduce Phase 1 E7, then catch it.
  - Run: `python phase02_internals/compactor.py --simulate --turns 60 --no-compaction`
  - Expected: the run stops at turn 42 with 32,635 tokens and the line "STOP: prompt exceeds the window. This is the E7 failure."
  - Then run: `python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5`
  - Expected: call 5 fails with a context-length error. The backstop compacts from 3,849 to 2,270 tokens, one retry succeeds, and the run continues. The summary line reports `backstops: 1`. The next line tells you to lower `--trigger-ratio`.
  - Teaches: the trigger is the fix. The backstop is the second layer. A backstop that fires is a bug report.

---

## 🔍 Check it yourself — questions against the course code

This course has no anchor repository. These questions use the exercise code you now have. The last question works on any repository.

1. Open `code/phase02_internals/compactor.py:142`. This is `ContextManager.render`. It joins the zones in a fixed order. Explain why moving `self.carry.render()` above the tools block would raise your bill. Use section 2.3 from part A. Then open `CarryOver` at line 98. Find the one field that the ConstraintRot results say must never depend on the summariser.
2. Open `code/phase02_internals/compactor.py:227`. This is `is_context_overflow`. List the checks in order. Then find the first `return False`. Explain what the function returns for a 500 error whose message contains "maximum context length". Say why that answer is safe for a retry loop.
3. Open `code/phase02_internals/batching_sim.py:122`. In chunked mode, `room` subtracts `len(decoding)` before any prefill is taken. Suppose the prefill took the budget first, and the decodes got what was left. Predict what happens to the worst gap. Explain which user sees the difference.
4. In any service you own that calls a model, run `grep -rn "max_tokens\|finish_reason\|response_format" <your repo>/`. For every call that sets `response_format` but never reads `finish_reason`, write down what happens when the answer is cut off.

---

## ✅ Checkpoint 2B — answer in your own words

1. **This is broken.** Your streaming support answers look fine on the dashboard. Median TTFT is 600ms and median total time is 4.2s. Users report that the text "stops for a second" in the middle. Nothing in your metrics shows it. (a) Name the server behaviour from section 2.4 that causes this. (b) Name the one metric you must add. (c) Your provider will not change its token budget for you. Name two things you can still change.

2. **Walk through what happens, and show the arithmetic.** A server uses the cost model from `batching_sim.py`. Three requests are decoding. A 24,000-token prompt arrives. The token budget is 2,048. (a) How long do the three streams freeze without chunking? (b) With chunking, how many tokens of prefill fit in each iteration, and how many iterations does the prompt need? (c) How long is each chunked iteration?

3. **This is broken.** Your classification service returns valid JSON that matches the schema on every call. `finish_reason` is `stop`. But accuracy dropped 9 points after you enabled strict mode last week. (a) Give the most likely cause from section 2.5. (b) Describe the exact schema change you would test, including its place in the property order. (c) Name the measurement that would settle it. Say why one run is not enough.

4. **Given these constraints, design** the context strategy. Your agent runs 200 tool-calling steps over several hours. A policy rule says it must never issue a refund above 200 EUR. Cover the trigger, the text you copy word for word, the summary, what you drop, and cost records. Use the ConstraintRot numbers to justify one choice.

5. **A colleague says:** "Compaction fixed our long-running agent. We compact at 60%, and tasks now finish." Give the counter-argument from the 2026 research in section 2.6. Name the finding about step count and context length. Say what you would measure to tell the two explanations apart.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) Another request's long prefill ran in one iteration without chunking. Every decoding request got no token during that pass. (b) The maximum inter-token gap per response, recorded while the stream runs. Median TTFT and total latency cannot show a freeze. (c) Shorten your own prompts, so your prefills are small. Move long-context work to a separate endpoint or a batch path. Then it does not share a batch with interactive traffic. A fallback provider for interactive traffic is a third option.

2. (a) The prefill-only pass costs 24,000 × 0.03 = 720ms. The three streams get no token for that pass. With the decode passes on each side, the measured worst gap in the default run is 764ms. (b) The budget reserves 3 tokens for the decodes, so 2,048 - 3 = 2,045 prefill tokens fit per iteration. 24,000 / 2,045 = 11.7, so the prompt needs 12 iterations. (c) 2,045 × 0.03 + 18 + 0.12 × 3 = 61.35 + 18.36 = 79.7ms. The streams now pause about 80ms per token instead of 720ms once. The measured worst gap is 81ms, because the real batch holds more decodes.

3. (a) The schema forces the label early. The model chooses a label with no room to reason in text first. (b) Add a `reasoning` string field as the first property, before the constrained fields. Add it to `required`, and keep `additionalProperties: false`. A `reasoning` field placed last changes nothing, because decoding runs left to right. (c) Run the same labeled set through both schemas with `structured_lab.py`. Fix and report the parser. One run is not enough, because sampling varies between runs. A 9-point gap can appear by chance on 12 items. Use `--repeat` and compare across runs before you trust the number.

4. Trigger at a fixed token threshold well below the window, for example 50% to 60%, checked before every call. Copy word for word: the refund limit rule, every other policy constraint, and the last few turns. Summarise: earlier conversation, into decisions, constraints, and open items. Drop: full tool results, replaced by pointers such as an order id you can fetch again. Justification: ConstraintRot measured 0% violations when the constraint survived compaction, and 38% when it was dropped. So the refund rule must never depend on a summariser's choice. Cost records: the summarising call is a second billed call, so add it to the same run record. Anthropic's compaction feature leaves those tokens out of top-level usage. A simple meter will count too little.

5. The 2026 study of 10,664 trajectories found that task success falls with the number of steps, not with context length. A smaller context window made the fall steeper, with a logit slope of -0.69 against -0.44. So the win may come from lower cost or from chance, not from fixing the decline. To separate the explanations, run two tests. Hold the step count fixed and vary the context length. Then hold the context length fixed and vary the step count. Measure task success in each. If success follows the step count in both tests, compaction was not the cause.

</details>

---

## References & Further Learning

Every link below was fetched and checked on 2026-09-12. Four pages were fetched again on 2026-09-17 and returned 200. They are the vLLM tuning guide, Let Me Speak Freely, The Format Tax, and the OpenAI guide. Read the first group before the lab.

### Read before the lab

- **Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve, Agrawal et al., OSDI 2024** — https://arxiv.org/abs/2403.02310
  Readable version: https://ar5iv.labs.arxiv.org/html/2403.02310
  Focus on: section 3 for why a long prefill raises inter-token latency. Section 4 for chunked prefills and the token budget. Section 5.4.1 with Figure 14 for the overhead. That overhead is the reason not to set the budget too low. This paper is the source of section 2.4.
  Numbers: without chunking, hybrid batches raised time between tokens 28.3x. Capacity rose 2.6x for Mistral-7B on one A100, and up to 6.3x for LLaMA2-70B on eight A40s, against Orca. Budgets: 512 tokens for a strict latency target, 2048 for a relaxed one.
  Section numbers come from the arXiv version and may differ by one.

- **vLLM optimization and tuning guide, official documentation** — https://docs.vllm.ai/en/latest/configuration/optimization.html
  Focus on: the chunked prefill part. Smaller `max_num_batched_tokens` values such as 2048 "achieve better ITL because there are fewer prefills slowing down decodes". ITL is inter-token latency. Higher values "achieve better time to first token". Quotes checked on 2026-09-17.
  Defaults confirmed against the v0.29.0 source tree on 2026-09-12: `enable_chunked_prefill` is `True`. `max_num_batched_tokens` is chosen at startup from the GPU class, not fixed.

- **Efficient Guided Generation for Large Language Models, Willard and Louf, the Outlines paper** — https://arxiv.org/abs/2307.09702
  Focus on: section 2.2 for the mask formula. Section 3 for the index that maps each state machine state to its set of legal tokens. That index keeps the mask cost about constant per step, instead of growing with the vocabulary size. This paper is the mechanism in section 2.5.
  Note: the timing comparison in section 3.2 is one plot from one timing run, and the authors hedge it themselves. Do not quote a speedup from it.

- **The Format Tax, Lee, D'Antoni, Berg-Kirkpatrick, April 2026** — https://arxiv.org/abs/2604.03616
  Focus on: section 4.2 for the split between prompt and decoder. Section 4.3 with Table 5 for the two fixes. This paper settles the debate in section 2.5 by separating the causes.
  Note: this is a preprint. No peer-review venue was found, so weigh it with that in mind.

- **Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents, June 2026** — https://arxiv.org/abs/2606.22528
  Focus on: the violation rates before and after compaction. This is the strongest number in section 2.6, and the reason the `constraints` list exists in `compactor.py`.
  Numbers: 1,323 episodes across seven model families. The violation rates in section 2.6 come from this paper. Abstract re-checked on 2026-09-17.

- **Context editing and compaction reference, Anthropic platform documentation** — https://platform.claude.com/docs/en/build-with-claude/context-editing
  Second page: https://platform.claude.com/docs/en/build-with-claude/compaction
  Focus on: the default triggers quoted in section 2.6. Also note two design details. Clearing tool results invalidates cached prompt prefixes. Compaction tokens are billed but are not in the top-level usage counts.

### Constrained decoding

- **XGrammar blog and paper, MLC** — https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar
  Paper: https://arxiv.org/abs/2411.15100
  Focus on: the split between context-independent tokens, computed in advance, and context-dependent tokens. The blog states that more than 99% of tokens are usually context-independent. It reports up to 3.5x faster mask generation on JSON schema and up to 10x on context-free grammars.

- **XGrammar-2, MLC** — https://blog.mlc.ai/2026/05/04/xgrammar-2-fast-customizable-structured-generation
  Paper: https://arxiv.org/abs/2601.04426
  Focus on: Structural Tag, a current approach to the constraint tax. The model writes free text. A trigger token turns on the constrained region, and the schema applies only there. vLLM exposes it as `structural_tag`.
  The blog reports compilation on complex JSON schemas dropping from 534ms to 5.37ms. No accuracy measurement is published for Structural Tag yet. Treat it as an engineering fix, not as proven quality.

- **JSONSchemaBench** — https://arxiv.org/abs/2501.10868
  Focus on: Table 3 for the compile times used in section 2.5, and Table 8 for accuracy. Its setup puts the reasoning field before the answer field. That is the ordering rule in section 2.5. Under that ordering, constrained decoding matched or beat unconstrained decoding.

- **Let Me Speak Freely?, Tam et al., EMNLP 2024 Industry Track** — https://arxiv.org/abs/2408.02442
  Focus on: Table 1, Table 7, and Table 8. Read Table 8 closely. It shows constraints helping classification, although the abstract does not say so. Read section 2 for the words "is assumed", about whether JSON mode uses constrained decoding. The rebuttals attack that weakness. Quote checked on 2026-09-17.

- **Say What You Mean: A Response to "Let Me Speak Freely", .txt, the Outlines authors** — https://blog.dottxt.ai/say-what-you-mean.html
  Focus on: the parser numbers. The same task scores 0.35 with a strict regular expression parser and 0.61 with a flexible one. The post also re-runs the original tests on the same model.

- **OpenAI Structured Outputs guide, official documentation** — https://developers.openai.com/api/docs/guides/structured-outputs
  Focus on: the "Supported schemas" section, before you design a schema. The supported keyword list changes, so bookmark the page. The page also states that outputs follow the key order of the schema. The old platform.openai.com URL now redirects here.

### Context management

- **Effective context engineering for AI agents, Anthropic, 29 September 2025** — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
  Focus on: the compaction section and the structured note-taking section. It names what to keep: architectural decisions, unresolved bugs, and implementation details.
  Note: it gives no numeric threshold. Do not repeat a threshold and credit it to this page.

- **Context Rot: How Increasing Input Tokens Impacts LLM Performance, Chroma Research, 14 July 2025** — https://www.trychroma.com/research/context-rot
  Focus on: the LongMemEval section. It compares a focused input of about 300 tokens with a full input of about 113,000 tokens. The study covers 18 models from the Claude, GPT, Gemini, and Qwen families.
  Note: the page shows the accuracy curves as charts. It gives no accuracy percentage at a specific token count. The often-repeated "30% drop" figure does not appear on the page. Do not quote it.

- **Lost in the Middle: How Language Models Use Long Contexts, Liu et al., TACL 2024** — https://arxiv.org/abs/2307.03172
  Focus on: Figure 5, the curve of accuracy against position that section 2.6 quotes. The models are old. The shape of the curve still applies.

- **Slipstream: Trajectory-Grounded Compaction Validation for Long-Horizon Agents, May 2026** — https://arxiv.org/abs/2605.08580
  Focus on: the validation gap, and the two results quoted in section 2.6.

- **TRACE: Toward Reliable Context Compression for Long-Horizon Agents, August 2026** — https://arxiv.org/abs/2608.06503
  Focus on: Figure 4, blocked and repeated actions after a compaction boundary.
- **Self-Compacting Language Model Agents, June 2026** — https://arxiv.org/abs/2606.23525
  Focus on: the rubric that decides when to compact. This paper is the counter-argument to token thresholds. Section 2.6 quotes its results.

- **How Fast Do Agents Rot?, August 2026** — https://arxiv.org/abs/2609.01660
  Focus on: the main finding. Success falls with step count, not with context length. A smaller context made the fall steeper, with a logit slope of -0.69 against -0.44.
  Scope: 10,664 trajectories and nine models, from 1.2B parameters to deployed proprietary systems.

---

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
  vLLM 0.29.0: no single default; H100 API server 8192, A100 2048
  measure MAX INTER-TOKEN GAP; TTFT and total latency cannot see a freeze

CONSTRAINED DECODING
  mask illegal tokens each step → shape guaranteed, stopping NOT guaranteed
  prompt only → no guarantee | json_object → valid JSON
  json_schema + strict → schema obeyed
  finish_reason still required: a truncated answer is a parse failure
  schema rules: every key in required, additionalProperties false,
    optional = union with null
  THE TAX: format request in prompt ≈ -3.9 pts, the decoder ≈ -1.6 pts
  reasoning field goes FIRST, or it does nothing
  fixes: two calls (+6.8 avg, worsens 3%), thinking (+9.2 avg, worsens 15%)
  report every tax number with its model and its parser

CONTEXT BUDGET AND COMPACTION
  zones with caps + headroom for the reply AND for the summarising call
  TRIGGER on a token threshold you chose, before the call
    compactor.py: 0.60 x 32,000 = 19,200 → fires at turn 25
    shipped: context editing 100k, compaction API 150k (min 50k)
  COPY WORD FOR WORD: constraints. 0% violations when kept, 38% when dropped
  SUMMARISE: decisions, open items.   DROP: tool results, keep pointers
  BACKSTOP: HTTP 400 + code context_length_exceeded → compact → retry ONCE
    never match on message text; never resend the same prompt unchanged
  compaction is billed: your summarising call is a second call
  400k-token prompt x 50 steps x $2.00/M (gpt-4.1) = $40 per conversation

THE COMMANDS (all offline except the live structured_lab run)
  batching_sim.py --token-budget N          structured_lab.py --self-test
  compactor.py --simulate --turns 40        compactor.py ... --no-compaction
  compactor.py --simulate --turns 12 --inject-overflow 5
```

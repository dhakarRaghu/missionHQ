You ship a streaming mode for your agent dashboard. The graphs look calm. Median TTFT is 600ms. Median total time is 4.2 seconds. Users report the text stops for a second, in the middle of an answer. No graph shows it. The same week, a classification call that worked for months starts returning JSON your parser rejects. Strict mode is on. And your longest agent run of the week dies at turn 42 with a 400 from the provider.

Three failures, each invisible in averages. Each has a server cause below the metrics you watch. This phase is those causes. It covers how prefill and decode share one forward pass, what a strict schema really guarantees, and how to budget a context window and compact it. It also pays two debts from Phase 1, where you met the 400 overflow and the truncated JSON on purpose.

- Prefill and decode share one forward passSo one long prompt either queues or freezes every other stream. You set the token budget, and you read the freeze in the max inter-token gap, not in TTFT.

- A schema controls which tokens are legal, never when generation stopsAnd most of the measured accuracy tax comes from asking for the format, not from the decoder. The fix lives in schema and prompt design.

- A bigger window does not remove the budget problemAccuracy falls with input length and position before the limit. So the window is split into zones, with headroom for the reply and for the summarising call.

- A summary keeps what the summariser found interestingRules that must survive cross the compaction boundary as literal text. The trigger is a threshold you chose, and the 400 is a bug report on it.

## What this builds on, and what it leaves for later

From Phase 1 you know the parts: tokens and pricing, prefill versus decode, the KV cache, TTFT and TPOT, sampling, and finish_reason. Two Phase 1 exercises set up this phase. E7 overflowed the context window and got a 400 back. E11 truncated a JSON answer and showed that finish_reason is the detector.

From Phase 2A you know the platform: the scheduler loop, continuous batching, the token budget, and the stable-first prefix rule. The sections below reuse the simulator's cost model at batching_sim.py:49. Two things are new here: vLLM's name for the budget, max_num_batched_tokens, and how the simulator shares it between prefill and decode. Use the same code directory and install step as part A.

THIS PART, AND THE FAILURE EACH SECTION PREVENTS

  chunked prefill               →  the stream that freezes mid-answer
  constrained decoding          →  the schema-valid answer that breaks the parser
  context budget + compaction   →  the long run that dies with a 400

Three things are named here and owned later. The bill and prompt caching belong to Phase 3A. Serving stacks and grammar backends belong to Phase 4A. Phase 5B reuses the gap measurements you record here.

Expect 1.5 to 2 hours. Three commands need no API key and no GPU: batching_sim.py, structured_lab.py --self-test, and compactor.py --simulate. The live structured-output runs need export OPENAI_API_KEY=sk-.... Any OpenAI-compatible endpoint also works, through --base-url and --key-env.

## Who freezes when a long prompt arrives?

Part A left one number without an explanation. In the continuous-batching run, the worst gap between two tokens of one answer was 764ms. Your user sees that gap as a frozen stream. This section is the cause.

Predict: three requests are decoding, and a 24,000-token prompt arrives. What happens to the three streams' next token?
Without chunking, the server has two bad choices, and it must pick one. Run the whole 24,000-token prefill in one iteration, and every decoding request gets no token during that pass. Or make the new request wait until the decodes finish, and its TTFT grows to seconds. Either way, someone freezes or waits. A frozen stream is not a slow model. It is a scheduling decision.

Go back to the scheduler loop from part A. One iteration runs one forward pass. That pass can do prefill work, decode work, or both. A new request arrives with a 24,000-token prompt. Without chunking, the two bad choices above are the whole menu.

Without chunkingWith chunking

NO CHUNKING — one large prefill stops every stream in the batch (example)

  iteration:      1      2      3           4           5      6
  prefill  :      -      -      -    [24,000 tokens]    -      -
  decode   :   A B C  A B C  A B C        none       A B C  A B C
  duration :    18ms   18ms   18ms        720ms       18ms   18ms
                                       ▲
                          A, B and C all freeze for 720ms here

CHUNKED — the same work, spread across iterations (example)

  iteration:    1        2        3        4        5        6
  prefill  :    -     2,045    2,045    2,045    2,045    2,045   ... (12 total)
  decode   : A B C    A B C    A B C    A B C    A B C    A B C
  duration : 18ms      80ms     80ms     80ms     80ms     80ms
                       ▲
         the new request's TTFT gets a little worse, and no stream freezes

Chunked prefill splits the prompt. Each iteration takes one slice of the prefill plus all the decodes. Both share one token budget. In vLLM that budget is max_num_batched_tokens. Set it to 2,048 with 3 decoding requests. The iteration spends 3 tokens on decode and up to 2,045 on prefill. The decodes are reserved first. batching_sim.py:122 computes room = max(token_budget - len(decoding) - prefill_tokens, 0). Without chunking, batching_sim.py:128 sets decoding = [], so no decode runs in that pass.

Every duration in those two drawings comes from three constants. Part A introduced them. Here they are again, because nothing below makes sense without them:

| constant | value | what it charges for |
|---|---|---|
| `MS_PER_PREFILL_TOKEN` | 0.03 ms | every prefill token in the pass |
| `BASE_DECODE_MS` | 18.0 ms | one decode step, whatever the batch size |
| `PER_SEQ_DECODE_MS` | 0.12 ms | each stream decoding in that step |

One pass costs `prefill_tokens × 0.03`. If any stream is decoding, add `18 + 0.12 × streams`. That is the whole cost model (`batching_sim.py:49`), and it produces every number above:

- three streams decoding, no prefill: 18 + 0.12 × 3 = **18.4ms**.
- the whole 24,000-token prompt in one pass: 24,000 × 0.03 = **720ms**.
- a 2,045-token slice plus the three streams: 61.4 + 18.4 = **79.8ms**.
- slices needed: 24,000 / 2,045 = 11.7, so **12 passes**.

Read the shape, not the values. Decoding three streams costs 18.4ms. Decoding one costs 18.1ms. Prefill is charged for every token it touches. Decode is charged once per step, almost regardless of how many streams share it. That asymmetry is the whole reason one long prompt is dangerous, and it is why slicing it works.

Why is a prefill slice nearly free next to the decodes? A decode iteration is memory-bound. Moving the KV cache and the weights dominates, and the compute units mostly idle. That idle compute is the slack a prefill chunk fills. The slack runs out at a knee, around 512 tokens on an A100. At high tensor-parallel degrees the knee moves to roughly 500 to 600 tokens, because fixed overheads grow.

Evidence
The knee values and the fixed fill order are from Sarathi-Serve (Agrawal et al., OSDI 2024), verified in the full text. The fill order is the paper's Algorithm 3: decodes first, then partial prefills, then new prefill chunks within the budget. The simulator's reservation line is faithful to it.

The fill order matters as much as the budget. Each iteration is packed in a fixed order. Finish every decode first. Then continue a partially-prefilled request. Then start a new prefill chunk with what remains.

A moment on the bigger picture. Disaggregating prefill and decode onto separate GPUs (Splitwise, DistServe) removes the freeze by never sharing the pass. It costs a KV transfer between machines. Co-located chunking is the lighter fix, and it is what production vLLM ships. The choice belongs to Phase 4.

So the freeze has a cause and a fix. What does the fix cost, and how do you see any of this in numbers you can act on? The next section measures both.

## How do you see the freeze in numbers you can act on?

You will be asked whether your streaming experience is healthy. TTFT and total latency cannot answer that. A stream can start fast, finish on time, and still sit silent for a second in the middle. The metric that answers is the maximum inter-token gap per response, recorded while the stream runs.

Run the comparison with a large prompt:

offline
python phase02_internals/batching_sim.py --long-prompt 48000 --rate 10 --requests 60

The course author's runs, not independently executed for this lesson:

│ policy     │ mean TTFT │ p99 TTFT  │ mean TPOT │ worst gap  │ throughput │
│ static     │    8690ms │   14526ms │    19.5ms │       20ms │   2.7 rq/s │
│ continuous │    3028ms │   7140ms │    25.5ms │     1460ms │   3.8 rq/s │
│ chunked    │    3140ms │   7242ms │    24.9ms │       81ms │   3.8 rq/s │

Chunking adds 3,140 − 3,028 = 112ms to mean TTFT. The worst gap between two tokens falls from 1,460ms to 81ms. That is 18x smaller. It is the number your users feel during a stream.

The budget sweep shows the same trade, with the default workload and only --token-budget changed:

Worst inter-token gap by budget, in the simulator's chunked row. The last row is the continuous policy. Smaller budget, better smoothness, worse TTFT. Bigger budget, the reverse.

This freeze is not a simulator artifact. It was measured on GPUs.

Evidence
Sarathi-Serve (Agrawal et al., OSDI 2024) mixed an unchunked prefill into a decode batch and measured the time between tokens. It rose up to 28.3x versus a decode-only batch, for Mistral-7B on one A100 with a 256-token budget (Figure 9a). The same shape held for LLaMA-2-70B on four A100s at a 512-token budget (Figure 9b). Capacity also rose with chunking: the abstract reports 2.6x for Mistral-7B on one A100 against vLLM. The simulator numbers above are the course author's runs, repeated with the same result before this lesson was written; they were not independently executed.

On a hosted API you cannot set max_num_batched_tokens. You still see the effect, and you can still act on it.

- Record the max inter-token gap per response, alongside TTFT and total time. An average hides a freeze. A maximum does not.

- Check your own client before you blame the provider. vLLM's stream_interval batches tokens before streaming when set above 1. Its default is 1 at v0.29.0. A value above 1 creates gaps that have nothing to do with prefill. Without gap metrics split by cause, you would misread a buffering setting as a scheduling stall.

- Keep your own prompts smaller. Your large prefill freezes other users' streams. On a single-tenant deployment, it freezes your own.

The sentence to remember: prefill and decode share the same forward pass. A long prompt either waits or freezes the other streams. Chunking decides which.

The trap: teams measure TTFT and total latency and call the stream healthy. Neither number shows an 800ms freeze in the middle of an answer. Add a maximum inter-token gap metric before you promise a streaming experience.

Try this now: run python phase02_internals/batching_sim.py --long-prompt 48000 --rate 10 --requests 60 and read the worst-gap column across the three policies. That column is the one your users feel.

One question is left open. The sweep moved the budget and the numbers moved with it. But what budget should you run, and does the engine even give you one by default? That is the next section.

## Who should pay: the new request, or the streams already running?

Chunking does not remove the cost of a long prompt. It moves it. The size of each slice decides who pays, and that is a decision about your product, not about your server.

**Predict: you halve the token budget so your chat streams feel smoother. Who is now worse off, and by how much?** The request with the long prompt. Its prefill is cut into twice as many slices. It waits through twice as many passes before its first token. The streams already running are better off: each pass they share is shorter. You did not make the server faster. You moved the wait from many users onto one.

The simulator run in the section above shows both ends of the dial. At a budget of 512 the worst gap in a stream is 35ms, and the mean wait for a first token is 1,094ms. At 8,192 the worst gap is 265ms, and the mean first-token wait is 908ms. One number falls as the other rises. There is no setting that wins both.

- **Chat, voice, anything streamed:** small budget. Someone is watching each token arrive. A smooth stream beats a fast first token.
- **Batch jobs, summarising, backfills:** large budget. Nobody is watching. Finishing long prompts quickly beats smoothness.

The dial does not go to zero. Splitting a prefill makes attention read the KV of the earlier slices again for every later slice. More slices means more of that repeated reading. Below some slice size you are paying for smoothness with prefill throughput, and the simulator does not model that cost.

One practical detail. vLLM has no single default for `max_num_batched_tokens`. It picks one at startup, from your GPU and from how you launched it. Read the real value from your startup log before you tune anything.

**The sentence to remember:** the token budget decides who waits. A small one protects the streams already running, and a large one protects the request that just arrived.

**The trap:** tuning the budget for throughput on a service people watch. Your averages improve and the stream stutters.

**Try this now:** run `python phase02_internals/batching_sim.py --token-budget 512` and then `--token-budget 8192`. In the chunked row, mean TTFT and worst gap move in opposite directions. That is the dial you are choosing.

You now control the freeze. The next failure is different in kind: the answer that is perfectly shaped and still wrong.

## What does strict mode actually guarantee?

In Phase 1 E11, a truncated JSON answer broke your parser, and the lesson was finish_reason. Here is the other half. A prompt that asks for JSON is a request, not a guarantee. Constrained decoding makes it one. It does not give you the other half of what you need, and teams that think it does ship silent breakage.

Predict: your service sets strict mode. Every response is schema-valid. Is your parser safe?
No. A schema constrains which tokens are legal at each step. It does not constrain when generation stops. If max_tokens runs out mid-object, you get a truncated document. It still follows the schema's shape. It still cannot be parsed. Shape is guaranteed. Completeness is not. finish_reason is still the only detector.

The mechanism sits between scoring and sampling. Decoding picks one token at a time. Before each pick, the model scores every token in the vocabulary. Those scores are the logits. Sampling then chooses one. Constrained decoding adds a step. For the current schema state, compute the legal-token set. Set every illegal token's logit to negative infinity. Those tokens get zero probability. The model can only choose a legal next token.

ONE DECODE STEP, WITH AND WITHOUT A GRAMMAR MASK (example scores)

  model logits        mask (from the schema)      masked logits
  ┌──────────────┐    ┌──────────────────┐        ┌──────────────┐
  │ "Sure"  4.1  │    │ illegal here  ✗  │   →    │ "Sure"  -inf │
  │ "{"     3.8  │    │ legal         ✓  │   →    │ "{"      3.8 │  ← chosen
  │ "Here"  3.5  │    │ illegal here  ✗  │   →    │ "Here"  -inf │
  │ "["     2.9  │    │ illegal here  ✗  │   →    │ "["      -inf │
  └──────────────┘    └──────────────────┘        └──────────────┘

  The state machine now moves to "expecting a key or }". The next step gets
  a different mask. Prose can never appear, because prose tokens are
  never legal at this state.

The mask comes from a state machine the engine builds from your schema. It reads the schema, builds the states, and computes for each state which vocabulary tokens are legal. Building it takes time, and the time depends on the library. Median grammar compilation, on the same schemas through llama.cpp: Guidance about 0.01s, XGrammar 0.11s to 0.30s, Outlines 3.48s to 8.05s. Some Outlines keywords take 40 seconds to minutes. That is roughly a 70x spread between medians.

XGrammar keeps this off your critical path. It precomputes the context-independent part of the mask, which is more than 99% of tokens for typical JSON schemas. It runs the rest alongside the prefill.

Evidence
Compile times are JSONSchemaBench's medians, measured on the same schemas through llama.cpp, verified in the full text. The precompute share is from the XGrammar team's writeup. On hosted APIs, OpenAI's structured-outputs page states that the first request with any schema pays extra latency while the API processes it, and later requests with the same schema do not. Older material saying the delay applies only to fine-tuned models no longer matches the page. The fine-tuned distinction on the page is about keyword support, not latency.

So on a hosted API, expect a first-call penalty with any new schema, on any model. Measure your own provider. Still define schemas once, at import time. A self-hosted engine pays the compile for each distinct schema regardless.

Put the three levels side by side:

Prompt only

Valid JSON: no. Correct keys: no. Prose wrapping: happens. First call: normal. Can still truncate: yes.

json_object mode

Valid JSON: guaranteed. Correct keys: not guaranteed. Prose wrapping: cannot happen. Can still truncate: yes.

json_schema, strict

Valid JSON: guaranteed. Correct keys: guaranteed. Enum values: guaranteed. Prose wrapping: cannot happen. Can still truncate: yes.

Read the last row of all three twice. A schema controls which tokens are legal. It does not control when generation stops.

"Strict mode guarantees my JSON, so responses are valid and parseable." A truncated-but-schema-legal answer parse-fails at 3am, and nobody connects it to max_tokens.

"Strict mode guarantees shape. Completeness is checked with finish_reason, every call, before the parser runs."

One caveat if you serve the model yourself. "The shape is guaranteed" is true of hosted strict APIs. On your own boxes it is engine-dependent. XGrammar, the first choice in vLLM's auto backend, is under-constrained in 38 of 45 JSON Schema Test Suite categories. It accepts some instances the schema should reject. Guidance was under-constrained in 1. The fallback between backends is silent. So the same schema can be both slower and looser on a different engine. Phase 4A owns the backend choice.

Three schema rules to get right on day one, plus the size limits people hit late:

- Every property appears in required.

- additionalProperties is false.

- An optional field is a union with null, like "type": ["string", "null"]. Do not leave the key out of required.

- OpenAI's bounds at the time of writing: the root must be an object, with no anyOf at root. At most 5,000 properties. At most 10 nesting levels. At most 120k characters of names, enum and const strings. At most 1,000 enum values. Unsupported keywords for all models include allOf, not, if/then/else, dependentRequired, dependentSchemas. Check the current page before you design.

So the guarantee is narrower than it looks, and the stopping point is yours to check. What strict mode does to answer quality is the next question, because the honest answer changed twice in two years.

## Where does the accuracy change come from?

Forcing a schema can change the quality of the answer, not only its shape. Most teams never measure it. The ones that did disagreed for two years. The disagreement has an explanation, and the explanation tells you where your fix lives.

Predict: accuracy dropped 9 points after you enabled strict mode last week. Every response is schema-valid and finish_reason is stop. Give the two most likely causes and the one schema edit you would test first, including where in the property order it goes.
Cause one: the schema forces the label early. The model must commit to the answer field before it has written any reasoning. Decoding is left to right, and the outputs follow the schema's key order. Cause two: the prompt asks for the format in words, which is itself the larger measured tax. The edit: add a free-text reasoning field as the first property, before the constrained fields. Put it in required. A reasoning field placed last changes nothing, because the answer is already chosen by then.

The measurement that settled the argument separated two things every earlier study had merged. It tested 6 open-weight and 4 closed-weight models, across 4 formats and 4 tasks:

Average points lost per effect. Of 39 result cells with a statistically significant effect, 36 showed the effect from the prompt request alone. Only 3 cells showed a drop from the decoder. So the tax is real. The decoder causes the smaller part of it.

Evidence
"The Format Tax", Lee, D'Antoni and Berg-Kirkpatrick, an April 2026 preprint with no peer-review venue found; abstract verified, body numbers carried from the phase author's reading. Two results from the same paper travel with it. Constrained decoding raised format validity from 55.7% to 92.2%, while accuracy moved from 57.3% to 55.7% against a 61.5% free-form baseline. The paper's summary: "higher compliance does not translate into better reasoning". The effect is also model-dependent: three newer closed models changed near zero or positively, while an older small model lost 5.2 points without constraints and 8.0 with them. The earlier dispute, a 2024 EMNLP paper reporting large drops versus an Outlines authors' re-run finding zero, resolved on two grounds: the original never confirmed providers use grammar decoding, and scoring was parser-sensitive.

That scoring warning is not a footnote. Switching the scorer from a rule-based extractor to a model judge dropped the same paper's average MATH-500 tax from 10.1 to 6.6 points. About a third of the measured tax came from the scoring, not the model. When you measure your own tax, fix the parser first. Report it with the number. A tax without its parser tells you nothing.

The ordering rule has a mechanical reason. Outputs follow the key order of the schema. Decoding runs left to right, so a field can only influence the fields after it. The lab's schema builds on this, from structured_lab.py:90:

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

With this ordering, reasoning before answer, one benchmark measured constrained decoding matching or beating unconstrained decoding on the same tasks. Under the opposite ordering, an earlier study found 100% of gpt-3.5-turbo JSON-mode answers put the answer key before the reason key. Same model, opposite result. Ordering is the difference.

If the reasoning field is not enough, two measured mitigations exist:

Two calls: answer freely, then reformat

Improved 42 of 72 cells, made 2 worse (3%), average gain +6.8 points. Costs one extra request. The safer choice.

Thinking enabled before the structured answer

Improved 43 of 72 cells, made 11 worse (15%), average gain +9.2 points. Larger gain on maths, does not help on writing.

Neither fix is free. Measure before you pick one, on your task, with your parser.

Where the same question lives in Mission HQ: open backend/src/hq/llm.py. It is the model registry, with per-model timeouts and output caps. Find a model call in the repo that reads finish_reason before the caller parses the reply. If there is none, trace what happens to the next agent step when a strict-JSON reply is cut off at an output cap. That gap is Phase 1 E11 wearing your own clothes.

The sentence to remember: constrained decoding masks illegal tokens at every step. The shape is guaranteed, the stopping point is not, and the accuracy tax is mostly a prompt tax that you measure per model and per parser.

The trap: reading an old article that says every new schema costs a first-request compile, or one that says structured output costs a fixed percent of quality. Both claims are stale. Measure your own pair of numbers and record the date.

Try this now: run python phase02_internals/structured_lab.py --self-test. No key needed. Confirm all six parser cases pass and the last line is "all self-tests passed".

That closes the second failure. The third one is slower. Nothing errors, nothing freezes. The agent just starts answering worse as the transcript grows, and the window is nowhere near full.

## Why does quality fall before the window fills?

Phase 1 E7 sent a prompt that was too large and got a 400. The obvious fix is a bigger window. It does not work, for three separate reasons, and each one has evidence. Skip this section and you will size contexts by the token limit, then wonder why long runs drift.

Predict: your needle-in-a-haystack eval passes at 2k tokens. The production transcript is 90k. Name the two things that got worse before the context limit was ever hit.
One: accuracy with input length. Retrieval of a fact falls as total tokens grow, even when the fact is present. The same needle is harder to find in a bigger pile. Two: accuracy with position. A fact in the middle of the window is read worse than the same fact at the start. Neither is a token-limit problem. A bigger window makes both worse, not better.

Reason one: accuracy falls as input grows. One study tested 18 models across the Claude, GPT, Gemini and Qwen families, on retrieval tasks at many input lengths. Performance fell as length grew, in every family. On LongMemEval, every model scored higher on a focused input of about 300 tokens than on a full input of about 113,000 tokens that contained the same answer.

Reason two: position inside the window matters. A study moved the needed document to different positions and measured accuracy at each:

20 documents, GPT-3.5-Turbo (0613), multi-document QA. The middle bar is the closed-book baseline. Mid-context performance is worse than having no documents at all. The 56.1% closed-book value is from the paper's Table 1. The other two are readings from its Figure 5 bars. The prose guarantees the shape, a drop of more than 20 points below closed-book, but not those decimals. The models are older. Treat the numbers as the shape of the effect, not as current values.

The same study's long-window check kills the easy escape. Long-window variants of a model, 16K and 100K versions, performed nearly identically to their short-window siblings within the same window. Capacity is not usage. A model with a bigger window does not read a big context better.

Evidence
The position study is "Lost in the Middle", Liu et al., TACL 2024, verified in the full text; the models date from 2023. The input-length study is Chroma's context-rot research, carried from the phase's own check of the study, not independently re-read for this lesson. Both papers support the same rule: accuracy falls with length and with mid-window position before any limit is reached.

Reason three: a full large window is expensive, every call. Cost grows with every input token, and a long agent loop re-sends the whole transcript each step:

What one long conversation costs in input tokens

Steps
Transcript size   tokens
Input price  $ per million tokens
Input cost

The default settings are the worked example from part A's pricing. A 400,000-token transcript over 50 steps at $2.00 per million input tokens is 20 million input tokens, or $40 for one conversation. The price shown is gpt-4.1, the deep role in prices.yaml. Phase 3A owns the full bill and prompt caching, which is the lever that cuts this.

So each extra token costs the same and helps less. The window is a budget to allocate, not a limit to fill. The next section allocates it.

## How do you split a window into zones?

A context window has a fixed size and several sources write into it. Without caps, the largest source takes the space, and the largest source is usually a tool that returned a large result. So the window is budgeted into zones with caps, like any other shared resource.

A worked budget for a 32,000-token window:

system — 1,000

Never changes. First in the prompt.

tools — 6,000

Changes on deploy only.

carry-over — 2,000

Written by compaction.

history — 10,000

Oldest turns leave first.

retrieval and tool results — 6,000

Truncate results, keep pointers such as an order id you can fetch again.

headroom — 7,000

For the reply AND for the summarising call.

People forget the last row most often. If you fill the window to the limit, the summarising call cannot run either. That call is the one that would fix the problem. Headroom is not slack. It is the space the recovery mechanism needs.

The zone order is not free either, and part A said why: the stable-first prefix rule. Zones that change rarely go first, so the KV cache and any prompt cache can reuse the prefix. System and tools change on deploy. History grows at the tail. The carry-over block is rewritten by every compaction, so it sits after the stable zones and before the volatile history. Moving the carry-over above the tools block invalidates the cached prefix on every compaction and raises your bill.

Shipped products set their numbers the same way, as fixed thresholds well below the window:

100,000default trigger, Anthropic context editing, which clears old tool results and keeps the last 3 tool uses

150,000default trigger, Anthropic server-side compaction; values below 50,000 are rejected

All three mechanisms you met in this section live in one question you can ask of your own code. Open backend/src/hq/memory.py and find trim_to_cap: a context budget enforced by dropping the oldest lines. Ask it: when the cap is tight, which lines go first, and where does an agent's standing rule written three days ago end up? Then ask what would have to be true for that rule to survive. The next section is the answer, and it is not "a bigger cap".

With zones capped and headroom reserved, the remaining question is the one users actually hit: what happens when the budget is exceeded anyway, and what crosses the boundary when you compact. That is compaction, next.

## What survives a compaction?

Compaction replaces old conversation turns with a shorter summary, so the prompt fits again. The dangerous part is not the summary being wrong. It is the summary being a summary. It keeps what the summariser found narratively interesting, and a policy rule is unremarkable prose.

Predict: your agent's run log shows a compaction boundary at turn 41 and a policy-violating tool call at turn 43. The same call was clean for 40 turns. What is your first hypothesis, and what one change to what crosses the boundary kills it?
Hypothesis: the compaction summarised away the policy rule. The call was clean while the rule was in the prompt. It violated the rule two turns after the rule left the prompt. The change: copy the rule across the boundary as literal text, never through the summary. Measured on ConstraintRot, violations stay at 0% when the constraint survives and sit at 38% when the summary drops it.

A summary is written for narrative salience, not invariance. A later turn cannot recreate three kinds of facts once they are summarised away: decisions, constraints, and open items. Constraints are the most dangerous to lose, because nothing errors when they leave. A benchmark called ConstraintRot measured exactly this. It ran 1,323 episodes across seven model families, graded by a program on tool calls, not by a model.

0% → ~30%tool-call policy violations, policy fully visible versus after compaction; up to 59% on some models

0% vs 38%violations when the constraint survives the summary versus when the summary drops it

0%violations with Constraint Pinning, the fix: constraints copied verbatim across the boundary

Evidence
ConstraintRot is from "Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents", a June 2026 preprint; abstract verified directly. The same paper documents a Compaction-Eviction Attack: adversarial content placed in the transcript can bias the summariser into evicting a legitimate policy. Compaction is not only a data-integrity problem. It is a prompt-injection channel into your safety rules, which matters for any guardrail work you do.

You have watched this failure in production, on a product with millions of users. In Claude Code, after a /compact, the instructions in CLAUDE.md are summarised away. Commit conventions and security rules stop being followed. The issue was closed as not-planned. The workaround users found is to say "read CLAUDE.md" after every compaction. That is constraint pinning, discovered independently by users.

Evidence
Claude Code issue #24460 on GitHub, opened and read directly. Observed on Opus 4.6, closed not-planned.

So treat it as an engineering rule. Decide what crosses the boundary as literal text before you decide what to summarise. The course's compactor does it like this:

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
  │ message 46  ─┐          │           │ message 46              │
  │ message 47   ├ kept     ┼──verbatim→│ message 47              │
  │ message 48   │          │           │ message 48              │
  │ message 49 ──┘          │           │ message 49              │
  └─────────────────────────┘           └─────────────────────────┘

The last few turns cross verbatim too. The agent is usually mid-task at the boundary and needs its immediate context intact.

The API you call may do some of this for you. Anthropic's on-demand compaction returns a signed compaction block with stop_reason: "compaction". That block must be sent first on every later request, and misuse is rejected with a 400 compaction_block_misplaced. Its pause_after_compaction flag lets your client insert blocks after the compaction, before the next turn. That pause is your pinning slot. Two documented footnotes travel with it. Clearing tool results invalidates cached prompt prefixes, so compaction interacts with your bill. And web-search tools inflate cache_read_input_tokens, which can make an SDK over-estimate the context and compact prematurely. A wrong trigger is a real, documented failure mode.

Evidence
Anthropic's on-demand compaction is a beta feature, enabled by the header compact-2026-09-04. The default triggers quoted in this part, 100,000 for context editing and 150,000 for server-side compaction, are from the platform's compaction and context-editing pages.

Where this lives in Mission HQ: open backend/src/hq/safety.py. It holds action classes, budgets, and HALT, enforced in code. Ask it: why do these checks live in code instead of the prompt? A summariser can drop a prompt line. What would it take for it to drop a rule from this file? The answer is the design lesson. Rules that must not move are not stored in anything a language model is free to rewrite.

The sentence to remember: a summary keeps what the summariser found interesting. Copy constraints, decisions and open items across the boundary as literal text.

The trap: "the model got lazy mid-session". The rule left the prompt, and the model obeyed the prompt it had. Measured violations jump from 0% to 38% exactly there.

Try this now: run python phase02_internals/compactor.py --simulate --turns 40 and read the compaction line. The trigger fires at turn 25. The prompt drops from 19,409 to 2,270 tokens. 45 messages are summarised and 4 kept verbatim.

The trigger fired because you set a threshold. What if the threshold was wrong, and the 400 arrives anyway? The next section is the second layer.

## What catches a trigger that was wrong?

The trigger can still miss. A tool can return far more than you expected, between two checks. So the design has a second layer. That layer has one rule most retry code in the wild gets wrong: never resend the same too-long prompt.

Phase 1 E7 is the failure being caught. A prompt over the window gets a fast 400. A blind retry resends the identical prompt and fails identically. Waiting changes nothing. The input has to change:

# The classic retry. It resends the SAME oversized prompt.
# The provider rejects it again, in about the same time, for the same reason.
for attempt in range(3):
    try:
        return client.chat.completions.create(model=m, messages=msgs)
    except Exception:
        time.sleep(2 ** attempt)   # waiting changes nothing here

# Change the input, then retry exactly once.
try:
    return client.chat.completions.create(model=m, messages=msgs)
except Exception as e:
    if not is_context_overflow(e):
        raise
    log.error("compaction trigger missed; backstop fired")   # this is a bug report
    msgs = compact(msgs)                                     # the input changed
    return client.chat.completions.create(model=m, messages=msgs)

This pair is a short illustration. The shipped version of the right pattern is at compactor.py:660 to compactor.py:671.

Detect the error by its machine-readable fields, not by its wording. The stable parts, in the order is_context_overflow checks them at compactor.py:227:

- HTTP status 400 first.

- Error code of context_length_exceeded.

- Error type of invalid_request_error.

- Message text last, because text is what providers change without notice.

A 429 or a 5xx is never an overflow, even when its text mentions maximum context length. The function returns False for them, so your retry loop keeps its normal backoff path. OpenAI's public error-codes page does not list context_length_exceeded at all. That is one more reason to match the fields and not the sentence. Anthropic's oversized input returns a 400 invalid_request_error with the text "prompt is too long", so the function matches Anthropic by type and text. The provider also documents 400 compaction_block_misplaced for on-demand compaction misuse, so the field-first habit holds there too.

Two costs and one honest limit, so you do not oversell the mechanism to yourself:

- Compaction is billed. Your summarising call is a second sampling call, and your meter must count it. Anthropic's compaction feature runs it as a separate iteration. Those tokens are not in the top-level usage counts. You add up usage.iterations to see the real total.

- Compaction is not free of risk. Three findings stack to the same point. Summaries validated off the main path recover accuracy. Repeated compression weakens the effect of recent turns. And long tasks fail by step count rather than context length, with a steeper decline on smaller windows. Compaction buys you a run that continues. It does not buy you a run that succeeds.

- Who decides when to compact is still open. A token threshold can fire at a bad moment, mid-derivation for example. Model-decided triggers, compact when a sub-task ends, are an emerging research idea. Thresholds are what ships, because you can test them.

Evidence
The three findings: Slipstream validates candidate summaries outside the main request path and recovers up to 8.8 points of accuracy. TRACE, on AppWorld, measures weakened recent-turn effects and more blocked and repeated actions after compaction boundaries. A study of 10,664 trajectories across nine models measures success falling with step count, not context length, and falling faster with a smaller window. All three rest on the phase's own abstract checks, not an independent re-read for this lesson.

The sentence to remember: compact at a threshold you chose, detect the overflow by its fields, change the input, retry once. A backstop that fires is a bug report on your threshold.

The trap: an alert that says "occasional 400s, retried successfully". A silent backstop hides a threshold that is too high. Log it loudly and lower the trigger.

Try this now: run python phase02_internals/compactor.py --simulate --turns 60 --no-compaction and watch the run stop at turn 42 with 32,635 tokens. Then run python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5 and read the backstop lines.

That is the third failure closed: the stream, the schema, and the window. The lab below runs all six exercises that prove them.

## The lab: six exercises, one per failure

Setup: cd ~/Desktop/project/code/study-material/inference-internals/code && pip install -e .. Three of the six need no API key and no GPU. Every offline command was run before this lesson was written and matched the numbers below. E8, E9 and E10 were not run against a live provider, because no key was on the machine. Run them and record what you see. Record every number: Phase 5B uses your gap measurements.

-  E4 offline proves c1 and c2 — the budget trade
Run: python phase02_internals/batching_sim.py --token-budget 512 then python phase02_internals/batching_sim.py --token-budget 8192.

Expected, in the chunked row: mean TTFT 1,094ms and worst gap 35ms at 512. Mean TTFT 908ms and worst gap 265ms at 8,192. The two numbers move in opposite directions. Then read the limit: the simulator does not model chunk-boundary overhead, so a very small budget has a real throughput cost the simulator hides.

-  E8 live · UNVERIFIED against a live provider · costs at most ~$0.02 proves c3 — measure your own constraint tax
Run offline first: python phase02_internals/structured_lab.py --self-test. Confirm all six parser cases pass and the last line is "all self-tests passed". Then: python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap.

Expected: prompt mode records at least one parse failure across 12 tickets. json and strict record zero. The accuracy column shows your tax, and the gap can be negative: a negative gap means the schema helped. Allow a first-call penalty on any model. The old expectation that only fine-tuned models pay it no longer matches the current documentation.

-  E9 live · UNVERIFIED against a live provider proves c3 — the reasoning field
Run: python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --reasoning-field.

Expected: output tokens, cost, and latency rise. Accuracy may or may not rise. Compare with E8 and decide whether the trade is worth it on this task.

-  E10 break-it · UNVERIFIED against a live provider proves c3 — shape without stopping
Run: python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --modes strict --reasoning-field --max-tokens 15.

Expected: the truncated column fills up. Parse failures appear, even though every answer followed the schema until it stopped. This is Phase 1 E11 with the proof attached.

-  E11 offline proves c5 — watch the trigger fire
Run: python phase02_internals/compactor.py --simulate --turns 40.

Expected: the prompt grows to 19,409 tokens and the trigger fires at turn 25 (threshold 0.60 × 32,000 = 19,200; first turn above it). The prompt drops to 2,270 tokens, 45 turns summarised, 4 kept verbatim. Then --trigger-ratio 0.3: threshold 9,600, fires three times, at turns 13, 23 and 33. Then --keep-last 10: one compaction at turn 25, down to 4,604 tokens, 10 kept verbatim.

-  E12 break-it · offline proves c5 — reproduce E7, then catch it
Run: python phase02_internals/compactor.py --simulate --turns 60 --no-compaction.

Expected: the run stops at turn 42 with 32,635 tokens and the line "STOP: prompt exceeds the window. This is the E7 failure." Then python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5: call 5 fails with a context-length error, the backstop compacts from 3,849 to 2,270 tokens, one retry succeeds, and the summary reports backstops: 1 and tells you to lower --trigger-ratio.

Four questions against the course code, to check you can read the mechanism and not just run it:

- Open code/phase02_internals/compactor.py:142, ContextManager.render. It joins the zones in a fixed order. Explain why moving self.carry.render() above the tools block would raise your bill, using the prefix rule from part A section 2.3. Then open CarryOver at line 98 and find the one field that the ConstraintRot results say must never depend on the summariser.

- Open code/phase02_internals/compactor.py:227, is_context_overflow. List the checks in order. Find the first return False. What does the function return for a 500 error whose message contains "maximum context length", and why is that answer safe for a retry loop?

- Open code/phase02_internals/batching_sim.py:122. In chunked mode, room subtracts len(decoding) before any prefill is taken. Suppose the prefill took the budget first and the decodes got what was left. Predict what happens to the worst gap, and say which user sees the difference.

- In any service you own that calls a model, run grep -rn "max_tokens\|finish_reason\|response_format" <your repo>/. For every call that sets response_format but never reads finish_reason, write down what happens when the answer is cut off.

## Check yourself: five scenarios

Answer in your own words before you open a sketch. Each one is answerable from this lesson alone.

- This is broken. Your streaming support answers look fine on the dashboard. Median TTFT is 600ms and median total time is 4.2s. Users report the text "stops for a second" in the middle. Nothing in your metrics shows it. (a) Name the server behaviour that causes this. (b) Name the one metric you must add. (c) Your provider will not change its token budget for you. Name two things you can still change.
Answer sketch(a) Another request's long prefill ran in one iteration without chunking, so every decoding request got no token during that pass. (b) The maximum inter-token gap per response, recorded while the stream runs. Also check your client's stream_interval before blaming prefill. (c) Shorten your own prompts so your prefills are small, and move long-context work to a separate endpoint or batch path so it does not share a batch with interactive traffic. A fallback provider for interactive traffic is a third option.

- Walk through what happens, and show the arithmetic. A server uses the cost model from batching_sim.py. Three requests are decoding. A 24,000-token prompt arrives. The token budget is 2,048. (a) How long do the three streams freeze without chunking? (b) With chunking, how many tokens of prefill fit in each iteration, and how many iterations does the prompt need? (c) How long is each chunked iteration?
Answer sketch(a) The prefill-only pass costs 24,000 × 0.03 = 720ms, and the three streams get no token during it. With the decode passes on each side, the measured worst gap in the default run is 764ms. (b) The budget reserves 3 tokens for the decodes, so 2,048 − 3 = 2,045 prefill tokens fit per iteration, and 24,000 / 2,045 = 11.7, so 12 iterations. (c) 2,045 × 0.03 + 18 + 0.12 × 3 = 61.35 + 18.36 = 79.7ms. The streams now pause about 80ms per token instead of 720ms once. The measured worst gap is 81ms, because the real batch holds more decodes.

- This is broken. Your classification service returns valid JSON that matches the schema on every call. finish_reason is stop. But accuracy dropped 9 points after you enabled strict mode last week. (a) Give the most likely cause. (b) Describe the exact schema change you would test, including its place in the property order. (c) Name the measurement that would settle it, and say why one run is not enough.
Answer sketch(a) The schema forces the label early. The model commits to an answer field with no room to reason in text first. (b) Add a reasoning string field as the first property, before the constrained fields, and add it to required with additionalProperties: false. A reasoning field placed last changes nothing, because decoding runs left to right. (c) Run the same labeled set through both schemas with structured_lab.py, fix and report the parser, and use --repeat. Sampling varies between runs, and a 9-point gap can appear by chance on 12 items.

- Given these constraints, design the context strategy. Your agent runs 200 tool-calling steps over several hours. A policy rule says it must never issue a refund above 200 EUR. Cover the trigger, the text you copy word for word, the summary, what you drop, and cost records. Use the ConstraintRot numbers to justify one choice.
Answer sketchTrigger at a fixed token threshold well below the window, for example 50% to 60%, checked before every call. Copy word for word: the refund limit rule, every other policy constraint, and the last few turns. Summarise earlier conversation into decisions, constraints, and open items. Drop full tool results, replaced by pointers such as an order id you can fetch again. Justification: ConstraintRot measured 0% violations when the constraint survived compaction and 38% when it was dropped, so the refund rule must never depend on a summariser's choice. Cost records: the summarising call is a second billed call, so add it to the same run record; on Anthropic's feature those tokens sit in usage.iterations, not the top-level counts.

- A colleague says: "Compaction fixed our long-running agent. We compact at 60%, and tasks now finish." Give the counter-argument from the 2026 research, name the finding about step count and context length, and say what you would measure to tell the two explanations apart.
Answer sketchThe study of 10,664 trajectories across nine models found task success falling with the number of steps, not with context length, and a smaller context window made the fall steeper. So the win may come from lower cost or from chance, not from fixing the decline. To separate the explanations: hold the step count fixed and vary the context length, then hold the context length fixed and vary the step count. Measure task success in both. If success follows the step count in both tests, compaction was not the cause.

## One screen to keep

CHUNKED PREFILL
  no chunking : one big prefill freezes every stream in the batch
  chunking    : prefill shares max_num_batched_tokens with the decodes
                decodes reserved first: 2048 - 3 decodes = 2045 prefill
  smaller budget → smoother stream, worse TTFT; larger → the reverse
  measured (simulator, chunked row): 512 → gap 35ms / TTFT 1094ms
                                      2048 → gap 81ms / TTFT 925ms
                                      8192 → gap 265ms / TTFT 908ms
  48k prompt: +112ms mean TTFT, worst gap 1460ms → 81ms (author's runs)
  real-GPU receipt: up to 28.3x TBT, Mistral-7B, one A100, budget 256
  budget floor: small chunks repeat attention work at boundaries
  vLLM v0.29.0 startup budget (arg_utils.py get_batch_defaults):
    B200/B300: 16384 both paths | H100/H200: offline 16384, API 8192
    A100 and smaller: offline 8192, API 2048 | throughput mode doubles unset
    max_num_seqs 1024 large-GPU path, 256 otherwise; chunked prefill ON
    DEFAULT_MAX_NUM_BATCHED_TOKENS=2048 is a test convenience, not a default
    queue caps (max_num_queued_reqs/tokens, default None) → 503 backpressure
  measure MAX INTER-TOKEN GAP; check stream_interval (default 1) first

CONSTRAINED DECODING
  mask illegal tokens each step → shape guaranteed, stopping NOT guaranteed
  prompt only → no guarantee | json_object → valid JSON, keys not guaranteed
  json_schema + strict → schema obeyed | truncation still possible
  finish_reason still required: a truncated answer is a parse failure
  self-hosted: XGrammar under-constrains in 38/45 test categories
    silent backend fallback changes latency (~70x medians) and strictness
  first request with ANY schema pays processing latency on OpenAI today
  schema rules: every key in required, additionalProperties false,
    optional = union with null; root object, ≤5000 props, ≤10 nesting,
    ≤1000 enums, ≤120k chars of names/enum/const strings
  THE TAX: format request in prompt ≈ -3.9 pts, decoder ≈ -1.6 pts
    model- and parser-dependent; report model AND parser with any number
  reasoning field goes FIRST, or it does nothing
  fixes: two calls (+6.8 avg, worsens 3%), thinking (+9.2 avg, worsens 15%)

CONTEXT BUDGET AND COMPACTION
  bigger window ≠ better reading: accuracy falls with length and position
    mid-context can score below closed-book (56.1% on the 20-doc task)
  zones with caps + headroom for the reply AND the summarising call
    stable zones first (prefix rule): system, tools, carry-over, history
  TRIGGER on a token threshold you chose, before the call
    compactor.py: 0.60 x 32,000 = 19,200 → fires at turn 25
    shipped: context editing 100k, compaction API 150k (min 50k)
  COPY WORD FOR WORD: constraints, decisions, open items, last turns
    0% violations when kept, 38% when dropped; pinning restores 0%
    compaction is also an attack surface (Compaction-Eviction)
  Anthropic on-demand compaction: compact-2026-09-04, stop_reason
    "compaction", pause_after_compaction = your pinning slot,
    misuse → 400 compaction_block_misplaced
  BACKSTOP: 400 + code context_length_exceeded → compact → retry ONCE
    never match on message text; never resend the same prompt unchanged
  compaction is billed: second call; Anthropic hides it in usage.iterations
  long runs fail by STEP COUNT, not context length
  400k-token prompt x 50 steps x $2.00/M (gpt-4.1) = $40 per conversation

THE COMMANDS (all offline except the live structured_lab runs)
  batching_sim.py --token-budget N          structured_lab.py --self-test
  compactor.py --simulate --turns 40        compactor.py ... --no-compaction
  compactor.py --simulate --turns 12 --inject-overflow 5

## Two things you could post

Your latency dashboard cannot see a frozen stream

Claim: TTFT and total latency pass while users watch a one-second mid-answer freeze, because prefill and decode share one forward pass. What makes it yours: you add max inter-token gap to your own agent platform and show the real gap trace from your own simulator runs, before and after the budget change.

Strict mode guarantees the shape, not the answer

Claim: a truncated reply is still schema-valid and still breaks the parser, and most of the accuracy tax comes from asking for the format, not enforcing it. What makes it yours: you measure the tax on your own classification task with your own parser fixed, and show the reasoning-field-first edit moving the number.

## Sources

- Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve, Agrawal et al., OSDI 2024. Full text: ar5iv. The freeze measurement, the fill order, the knee.

- vLLM v0.29.0, vllm/engine/arg_utils.py and vllm/config/scheduler.py. The startup budget table, the queue caps, the test-only constant.

- OpenAI Structured Outputs guide. Key order, first-request latency for any model, schema rules and size limits.

- The Format Tax, Lee, D'Antoni and Berg-Kirkpatrick, April 2026 preprint. The prompt-versus-decoder split, the mitigations, the scoring caveat.

- JSONSchemaBench. Grammar compile times, the reasoning-first ordering result, the under-constraint comparison.

- XGrammar, MLC blog. The context-independent precompute share.

- Lost in the Middle, Liu et al., TACL 2024. Position effects, the closed-book comparison, the long-window twin result.

- Governance Decay, June 2026 preprint. ConstraintRot violation rates, Constraint Pinning, the Compaction-Eviction Attack.

- Anthropic compaction and context editing. Default triggers, on-demand compaction, the billing and cache footnotes.

- Claude Code issue #24460. The production case of constraints summarised away by /compact.

- microsoft/sarathi-serve README.
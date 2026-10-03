Phase 2A gave you the scheduler loop, the token budget and the paged KV cache, so you can now say whose token runs next and how many requests fit in memory. But it ended on a number it could not explain: a worst gap of 764ms between two tokens of one answer. Your dashboard shows median TTFT at 600ms and median total latency at 4.2s, so every chart stays green while your users watch text stop mid-sentence for a second. Averages hide pauses, and this phase opens with the pause.

The same support agent then fails twice more in ways no average shows. You turn on strict schema mode for a classifier and lose 9 accuracy points instead of gaining reliability. A six-hour agent run dies on the same length error you provoked on purpose in Phase 1, and a retry loop resends the identical prompt into the identical rejection. This phase answers three questions: what freezes a stream when the metrics look healthy, why a format rule can cost accuracy before it ever constrains a token, and how an agent's rules and its retries behave when the prompt outgrows the window.

This lesson teaches five ideas. They are listed here so you can see where it is going, and they will read more clearly once each has been explained below, so come back to this list at the end.

- Prefill and decode share one forward pass and one token budget, so a long prompt either waits or freezes every stream in the batch, and chunking converts that freeze into a small TTFT tax. Explain any mid-stream freeze, choose a token budget for his product, and know which metric to add.
- A grammar mask guarantees which tokens are legal at each step and never when generation stops, so strict mode and finish_reason are independent checks and valid schema does not mean parseable answer. Keep the finish_reason check under strict mode, and diagnose parse failures that appear exactly when prompts are longest.
- Most of the measured accuracy cost of structured output is paid at the prompt, before any decoder constraint runs, so the fix is to let the model reason before the schema forces it to commit. Attribute an accuracy drop to the right cause, test the reasoning-field fix in one afternoon, and refuse any tax number that names no model or parser.
- A compaction summary keeps what the summariser found interesting, so standing constraints are the first content to die; constraints must cross the boundary as literal pinned text. Decide what is copied word for word across a compaction boundary before deciding what is summarised.
- A prompt over the window is rejected deterministically: the same input returns the same 400 at the same speed every time, so waiting between retries cannot change the answer. Separate deterministic input errors from transient load errors, and predict which of his retry loops will succeed and which will burn calls forever.

## The 764ms the dashboard cannot show

Phase 2A ended with a number nobody explained: a gap of 764ms between two tokens in your batching simulator. The dashboard around it was green. That gap is where this phase starts.

Your support agent now has three failures its metrics cannot see. Users report the text freezing mid-sentence while median TTFT and total latency look healthy. The new strict-mode classifier returns perfectly shaped JSON and lost 9 accuracy points the day you turned it on. And a long agent run ended on a 400 error. It was the same 400 you provoked on purpose in Phase 1. You sent a prompt larger than the context window. Three failures, three green dashboards.

This phase builds on five ideas you already have. Each comes back in one clause, because you read them days ago.

  The scheduler loop

From Phase 2A: the server never runs one request. It runs a loop, and each iteration is one forward pass over a batch. Your request shares every iteration with other people's requests.

  Prefill and decode

Prefill is the pass that reads your whole prompt at once. Decode is the loop that emits one token at a time. A request does its prefill once and its decode many times.

  TTFT and TPOT

TTFT is the time from sending the request to the first token coming back. TPOT is the time per output token after that. Both are averages, and this phase shows what an average cannot see.

  finish_reason

From Phase 1: every response carries a field saying why generation stopped, normally stop or length. It is the difference between an answer and an incident, and it comes back when strict mode enters.

  The context window

The model has a fixed maximum input size. In Phase 1 you sent a prompt larger than the window. The provider answered 400 immediately, before any token was generated.

These five ideas explain how a request moves through a healthy server. They do not yet explain a freeze with green metrics. They also do not explain an accuracy drop under a correctness feature, or the right response to an overflow. That is the work of this phase, and it happens in an order.

- The freezewhy one long prompt stalls every stream, and the budget split that fixes it

- The schemawhat strict mode guarantees per token, and what it can never guarantee

- The accuracy dropwhere the 9 points actually went, and the one-afternoon fix

- The growing promptcaps, compaction, and what must cross the boundary word for word

- The 400why the same oversized input fails identically forever, and the only correct retry

Phase 2A showed that one iteration is one forward pass doing prefill work, decode work, or both. The next section asks the question the 764ms gap leaves open. What happens to every decoding stream when one iteration is all prefill?

## Why does one long prompt freeze every stream?

One long prompt can stop every stream in the batch, and your averages hide it.

The orientation ended on a blind spot. The client receives TTFT, TPOT and finish_reason, and none of the three measures the time between two tokens. Phase 2A's simulator closed with an unexplained 764 ms gap of that kind. Users of your support agent now report the same symptom in production. Text stops mid-sentence and continues a moment later. You cannot fix what your numbers do not show, so this section finds the mechanism behind the gap.

Go back to the scheduler loop from Phase 2A. The server runs one iteration after another. One iteration is one forward pass, a single run of the model over the whole batch. Each pass does prefill work, decode work, or both. Prefill is the pass that reads the whole prompt at once. Decode is the pass that writes one token per waiting stream. Both kinds of work share the pass, so whatever fills the pass decides what every stream gets next.

- pickthe scheduler chooses the requests for this iteration

- forward passone run of the model over prefill and decode tokens together

- emiteach decoding stream appends its next token

The two kinds of work cost very different time. Decode writes one token per stream, so the pass mostly reads the model's weights from memory. The phase's cost model prices a decode iteration at 18 ms plus 0.12 ms per stream. It charges 0.03 ms per prefill token, so 24,000 tokens cost 720 ms.

Now a request arrives with a 24,000-token prompt, and three streams are mid-answer. Your dashboard shows a median TTFT of 600 ms and a median total latency of 4.2 s. TTFT is the time from sending a request to its first token back.

Predict: why do TTFT and total latency show nothing, and what one metric do you add?
Both numbers are medians over many responses. A median moves when half of all responses move, and one frozen stream in a hundred does not qualify. TTFT also stops measuring at the first token. A hole in the middle of an answer sits outside its view. The one metric to add is the maximum gap between two tokens of a single response. What carves the hole is the rest of this section.

The arrival forces one decision on the scheduler, because prefill and decode share the pass. There are two ways to place the prefill, and both are bad.

- Where does the 24,000-token prefill run?

- whole, in the next passthe three streams get zero tokens for 720 ms

- after the running answersthe new request's TTFT stretches to seconds

Choice one runs the whole prefill in the next pass. That pass takes 720 ms, and the three decoding streams get zero tokens during it. From the user's chair, the text stops mid-sentence for almost a second.

  The whole prefill in one pass

  Iterations 1 to 3: only decodes run, at about 18 ms each.

  Iteration 4: the prefill takes the pass, and streams A, B and C emit zero tokens for 720 ms.

  Iteration 5: the decodes resume at 18 ms, and the users saw one long pause.

  Durations computed from the phase's cost model: 18 ms per decode iteration and 720 ms for the whole prefill. Illustration, not measured on a GPU.

Choice two keeps the prefill out of the decode passes and lets the running answers finish first. The three streams stay smooth, but the new request's TTFT waits behind whole generations, so it stretches from milliseconds to seconds. TPOT, the time per token after the first, stays healthy the whole time, because it only counts tokens that already arrived.

Now the green dashboard reads differently. A 720 ms hole inside one response moves neither median, because medians need half the traffic to move. Total latency grows once, for the unlucky responses, and the median hides even that.

This freeze is not a simulator artifact. The Sarathi-Serve paper mixed a full prefill into a decode batch on real GPUs. It measured the time between tokens rising by up to 28.3 times against a decode-only batch, with Mistral-7B on one A100 and LLaMA2-70B on four A100s. The phase's run of batching_sim.py with a 48,000-token prompt shows the same shape. Its worst gap is 1,460 ms without chunking and 81 ms with it.

Evidence
Sarathi-Serve, OSDI 2024, section 4.2, Figure 9, read 2026-09-28. Its words: "Naive hybrid batching leads to dramatic increase of up to 28.3× in the TBT latency compared to a decode-only batch." TBT stands for time between tokens. The simulator numbers come from the course's batching_sim.py (continuous policy, 48,000-token prompt, 60 requests, rate 10); they show the shape and are not a GPU measurement.

The lab's E4 runs this simulator at a token budget of 512 and again at 8,192. Read the chunked row and answer which way mean TTFT and the worst gap each move.

  One long prompt must wait, or it freezes every stream sharing its forward pass.

  Mean TTFT and total latency cannot show a 720 ms pause inside one stream.

  Run batching_sim.py --token-budget 512 and compare its worst gap with the 764 ms.

Neither choice is acceptable, so the scheduler needs a way to run both kinds of work at once. The next section asks how sharing one token budget removes the freeze.

## How does sharing one token budget remove the freeze?

The last section left the scheduler with two bad choices. Run the prefill in one pass and the three decoding streams freeze for 720ms. Make the new request wait and it pays a very long TTFT. The third choice splits the prefill, so each pass holds a slice plus the decodes.

Chunked prefill splits one long prompt into slices and runs one slice per iteration. Every iteration still runs one forward pass, the sweep through the weights that produces each token. But the pass now holds a prefill slice alongside all waiting decodes. Both sides draw from one shared token budget per iteration. vLLM exposes this budget as the setting max_num_batched_tokens, sized in tokens per iteration.

  The same prompt, sliced into the budget

  Step 1: only the three decodes run, so the pass costs 18ms as before.

  Step 2: the decodes reserve 3 tokens, and the pass fills the other 2,045 with the first slice.

  Step 6: half the prompt is done, and no stream has missed a token.

  Twelve such iterations finish the prompt, and no gap exceeds 80ms. Illustration from the lesson's cost model, not measured.

prefill slicedecodewaiting

The order inside each iteration is fixed, and it is what keeps every stream producing tokens.

- reserve decodesone token for each of the three waiting streams

- fill with prefill2,048 minus 3 leaves 2,045 tokens of slice

- run one passslice and decodes together, about 80ms

Your simulator encodes this order in one line at batching_sim.py:122. Decode tokens leave the budget before prefill asks for room.

room = max(token_budget - len(decoding) - prefill_tokens, 0)  # batching_sim.py:122

Compute it yourself: three streams decode under a 2,048-token budget when a 24,000-token prompt arrives. How many prefill tokens fit in one iteration, and how many iterations does the prompt need?
The decodes reserve 3 tokens, so the pass has 2,045 left for prefill. Dividing 24,000 by 2,045 gives 11.7, so the prompt needs 12 iterations.

Now price one sliced iteration with the cost model from Phase 2A. A prefill token costs 0.03ms, so the 2,045-token slice costs 61.35ms. The three decodes cost 18 + 0.12 × 3 = 18.36ms on top. The whole iteration takes 61.35 + 18.36 = 79.7ms, which rounds to about 80ms. Twelve slices spread the same work across 960ms, and each stream still gets a token every 80ms.

  How many slices a prompt needs

  Token budget

  Decoding streams

  Prompt tokens

  Prefill per iteration

  Iterations to finish prefill

The run reported in your phase compares the two policies on a 48,000-token prompt. The freeze of 1,460ms became a worst pause of 81ms. The price was 112ms more mean TTFT, and each new long prompt pays it once.

  1,460 → 81 msworst gap between two tokens

  +112 msmean TTFT of new long prompts

  3.8 rq/sthroughput, unchanged

Evidence
Numbers from the run reported in your phase: batching_sim.py --long-prompt 48000 --rate 10 --requests 60, chunked row against the continuous row. The simulator shows the shape of the trade, not a GPU measurement. The hardware measurement of the freeze itself (28.3x, Sarathi-Serve) is in the previous section's evidence.

Phase 2A's prefix caching helps the same arithmetic. A prefix is the start of a prompt whose keys and values the server kept from an earlier request. A cache hit turns that request's prefill cost into almost nothing. Its TTFT falls, and the freeze it would inflict on other streams shrinks with it.

Chunking is the fix inside one instance. A scale-out fix is prefill/decode disaggregation, where prefills and decodes run on different instances. No pass ever mixes the two, so no stream can freeze. The cost is moving each request's KV cache from the prefill machine to the decode machine. Chunking is enough until Phase 4, when your agent gets its own GPU and the choice becomes real.

The lab's E4 runs batching_sim.py at a budget of 512 and again at 8,192. Watch the chunked row and answer which way mean TTFT and the worst gap each move.

  Reserve decodes first, then fill the pass with prefill slices, and the freeze is gone.

  Mean TTFT stays green through a freeze, because an average cannot show one 720ms pause.

  Run batching_sim.py --token-budget 512 and watch mean TTFT rise while the worst gap falls.

Smaller budgets make smoother streams, so the question is how small the budget can go. The next section answers why you cannot push it to zero.

## Why can you not push the token budget to zero?

A budget too small makes every stream smooth but burns throughput on repeated work.

The last section gave you the lever, the token budget in `max_num_batched_tokens`. Smaller gave smoother streams. The natural move is to push it toward zero. This section shows why that move fails.

Remember what one chunk does. A chunk of the prefill reads its own tokens. It also attends to all earlier tokens of the same prompt. Their keys and values sit in the KV cache, the per-request attention state the GPU keeps. So chunk N re-reads the KV of chunks 1 to N-1 before it can do its own work.

That re-read is the repeated cost. Cut the budget in half and the number of chunks doubles. Each one walks the same earlier KV again. On top of this, launching a chunk has a fixed kernel overhead. With many small chunks, that fixed cost repeats many times.

  Chunks and re-read for one prompt

  Prompt tokens

  Token budget

    Chunks  · total KV tokens re-read

Move the budget slider down and two numbers rise together. The chunk count rises. The total KV re-read rises with it, because each new chunk walks the same earlier KV again. At a 512-token budget the 24,000-token prompt needs 47 chunks and re-reads half a million KV tokens of its own prompt. At 2,048 it needs 12 chunks and re-reads a quarter of that. This re-read is why small budgets cost throughput.

Sarathi-Serve measured the cost on real GPUs. At a 512-token budget, chunking cost about 25% overhead on Yi-34B. At 2,048 the overhead was nearly negligible. Your simulator shows the same shape from the user side. The worst gap falls as the budget falls, and mean TTFT climbs at the same time.

Notice that the trade is not one-dimensional. From 8,192 down to 2,048, the worst gap improves 3x and mean TTFT barely moves. From 2,048 down to 512, the gap improves 2x again but mean TTFT starts climbing fast. Somewhere near there the paper's 25% overhead stops being worth the smoothness. Below that floor you buy smoothness with throughput, iteration after iteration, on every prompt in the system.

Evidence
Sarathi-Serve (OSDI 2024), section 5.4.1: "even with the smallest chunk size of 512, we observe a moderate overhead of at most ~25%" on Yi-34B with tensor parallelism of 2, and "with the larger token budget of 2048, chunked prefills have almost negligible overhead". The bar values come from your own `batching_sim.py` runs (40 requests, 6 per second, only `--token-budget` changed).

Because the trade has a floor, the budget is a product decision. A chat or voice product lives or dies on inter-token smoothness, so it takes a small budget and pays the TTFT. A batch job that summarises documents overnight has nobody watching the stream, so it takes a large budget and keeps the throughput. There is no correct number, only a correct direction per product.

Carry one fact into Phase 4, when the GPU is yours. In vLLM 0.29.0 there is no single default for `max_num_batched_tokens`. The engine resolves it at startup from the GPU class and the usage context: 16,384 on a B200, 8,192 on an H100 through the API server, and 2,048 on an A100. The constant `DEFAULT_MAX_NUM_BATCHED_TOKENS` exists for tests, and the source says so. The flag `enable_chunked_prefill` defaults to `True` for generator models and is forced off for encoder-decoder models.

Small budgets smooth the stream but re-read the KV at every chunk boundary, so the budget has a floor.

Pushing the budget toward zero looked free in the gap column, but Sarathi-Serve measured up to about 25% overhead at 512 on Yi-34B.

Re-run batching_sim.py at 512 and 8192 and check that mean TTFT and worst gap move in opposite directions.

The floor, the trade and the defaults are all server-side facts. Your support agent does not run on your server; it runs on a hosted API. The next section asks what is left under your control when the budget belongs to your provider.

## What can you do when the budget belongs to your provider?

You now know the budget that decides between a freeze and a wait, and you know its floor. Both facts live on the server. Your support agent calls a hosted API, so the budget belongs to your provider. This section looks at what remains under your control.

Chunked prefill, splitting a long prefill into slices that share each iteration's token budget, is a server configuration. You cannot set it for another company's GPU, and you cannot read its value. What you can control is what you measure and what you send.

Start with measurement. Your dashboard tracks TTFT, the time from sending a request to the first token coming back, and total latency. Both are averages over a whole response. A freeze is a pause between two tokens inside one response, so neither metric touches it. Three hundred tokens can arrive 25ms apart, one pair can sit 800ms apart, and the median per-token time stays 25ms. The dashboard is green because the metric it shows cannot express the failure.

The fix is one more number per response: the max inter-token gap. That is the longest pause between any two consecutive tokens in that stream. You already receive every chunk's arrival time from the streaming client. It is the same clock you used to measure TTFT in Phase 1. Recording the maximum difference between two arrivals costs a few lines of code and no extra API calls. A stream health alert then reads "max gap above 500ms". This is the condition your users describe as text stopping mid-sentence.

last = None
worst = 0.0
async for chunk in stream:
    now = time.monotonic()
    if last is not None:
        worst = max(worst, now - last)
    last = now
metrics.record("max_inter_token_gap_ms", worst * 1000)

The second lever is your own prompt size. The freeze comes from prefill and decode sharing one forward pass, and the freeze length grows with the prefill length. Your 24,000-token prompt does not freeze your own stream, because your stream is the one being prefilled. It freezes the other tenants in the provider's batch. This is the same way this phase's 24,000-token prompt froze streams A, B and C. You cannot see those victims and neither can they name you. But the mechanism is symmetric, so every large prompt you send is somebody else's 720ms pause. Trimming a prompt before sending it is not politeness. It is the same scheduling physics applied to the one variable you own.

25 msmedian per-token time, healthy

800 msmax inter-token gap, the freeze the median hides

0 linesof server config available to you on a hosted API

EvidenceThe freeze itself is measured, not simulated. Naive hybrid batching raised time between tokens up to 28.3x against a decode-only batch. The result covers Mistral-7B on one A100 and LLaMA2-70B on four A100s (Sarathi-Serve, OSDI 2024). Your own simulator showed the user-visible version: continuous batching's worst gap was 1,460ms while its mean TPOT stayed near 25ms.

So the division of labour is clear. The provider owns the budget, the chunking and the defaults. You own the per-response gap metric, which is the only number that sees a freeze. You also own the prompt size, which is the only freeze length you control. A green dashboard without the gap metric tells you about the start and the end of an answer. But the user experiences the middle.

On a hosted API you cannot chunk, but you can measure the gap and shrink your prompt.

Median TTFT and mean total latency cannot express an 800ms pause between two tokens.

Add the max-gap line to your streaming client and check it against one long answer.

The stream is smooth again, or at least observable. That closes the first failure of the running case. The lesson follows the agent to the second one, the strict-mode classifier that lost 9 accuracy points. The next section asks how the server enforces a schema at all.

## How does the server enforce a schema?

Strict mode changes which tokens can come out, and knowing exactly how is how you trust it correctly.

The stream is smooth again after chunking, so the lesson follows the agent to its next failure. The new strict-mode classifier was supposed to guarantee a clean answer, and it lost 9 accuracy points instead. The accuracy question comes later in this phase. First you need to know what strict mode actually does, because its guarantee turned out to be narrower than the team believed.

Your classifier sends 12 labeled ticket types to the model and expects `{"category": ..., "priority": ...}` back. With strict mode on, the parser stopped crashing. Then the accuracy dropped, and the team did not know which blame was right. You cannot answer that until you can say precisely what the server enforces.

### The picture first

Decoding picks one token at a time. Before each pick, the model scores every token in its vocabulary. These scores are logits, one number per vocabulary token. A sampling step then turns the scores into a probability and chooses one token.

Constrained decoding inserts one step between the scores and the pick. It builds a state machine from your schema, and the state machine knows which tokens are legal right now. The grammar mask is that list, and the engine applies it by setting every illegal token's score to negative infinity. Those tokens then have zero probability, so the model can only pick a legal one.

- model scoresone logit for every vocabulary token

- maskthe state machine marks illegal tokens, and each gets negative infinity

- sampleone token is chosen from the tokens that remain legal

- the state movesthe new token updates the state, so the next step gets a different mask

The mask changes at every step, and that is why prose can never appear. The model may want to write "Sure, here is your ticket". Those tokens are illegal while the state machine expects a JSON object. Their score is negative infinity, and the caller never sees them.

Predict: every response matches the schema, yet 4% crash your parser on the days prompts are longest. Strict mode is on. Where do you look?
Look at truncation, not at the schema. The mask guarantees that each emitted token is legal at its step. It does not guarantee that generation finishes. When prompts are longest, `max_tokens` runs out more often, and the answer is cut mid-object. `finish_reason` returns "length" for those responses, and that is the field your parser path should check.

### One decode step, close up

Here is one step from the classifier. The state machine is at the start of the object, so only `"{"` is legal. The table shows what the model wants and what the mask leaves.

tokenmodel logitlegal hereafter the mask

"Sure"4.1no−inf

"{"3.8yes3.8, chosen

"Here"3.5no−inf

"["2.9no−inf

After `"{"` is chosen, the state moves to "expecting a key or }". The next step gets a new mask for that state. This continues until the model emits the closing brace and an end token.

### Where the mask comes from

The engine builds the state machine from your schema. It reads the JSON Schema, builds the states, and computes the legal vocabulary tokens for each state. Libraries like XGrammar, Guidance and Outlines do this work, and vLLM and SGLang call them inside.

Building the state machine takes time the first time a distinct schema is seen. On a self-hosted engine, note two things. The compile cost is paid once per distinct schema, so define your schemas once at import time. And a self-hosted engine can silently fall back to a different backend when your schema uses an unsupported keyword, which changes the latency without an error message.

On a hosted API, the provider may charge the same first-call latency or may not, and the documented behaviour changes over time. The durable advice is to measure. Call the API once with a new schema and compare the first-call latency against the steady-state latency. That one measurement tells you what your provider does today.

### The three levels, and the row to read twice

prompt onlyjson_objectjson_schema, strict true

valid JSONnot guaranteedguaranteedguaranteed

correct keysnot guaranteednot guaranteedguaranteed

values within enumnot guaranteednot guaranteedguaranteed

prose wrappinghappenscannot happencannot happen

first-call costnormalnormalengine compiles the grammar

can still truncateyesyesyes

Read the last row twice. Strict mode controls which tokens are legal, and it does not control when generation stops. In Phase 1 exercise E11 a truncated JSON answer broke your parser, and strict mode does not remove that failure.

Strict mode masks illegal tokens at every step, so the shape is guaranteed and nothing else is.

"Strict mode is on" sounds like "the answer parses"; a truncated answer follows the schema and still cannot be parsed.

Time one first call with a fresh schema against the next call; a large gap means your provider compiles it.

Evidence
The mask mechanism is stated as an equation in The Format Tax paper (2026 preprint, section 2): the masked probability is proportional to the model's probability times an indicator that the token is valid under the grammar. The first-call compile advice comes from the phase; a specific quote about which provider models pay the delay could not be re-verified this run and stays off the page.

The mask guarantees that every emitted token is legal. But a document can follow the schema at every step and still be cut in half when the token budget runs out. The next section asks what the mask cannot guarantee: who says the answer is complete?

## Strict mode says the tokens are legal. Who says the answer is complete?

Strict mode guarantees legal tokens at every step, and the cut point is not one of them.

The section above showed the mask deciding which tokens are legal in the current schema state. The table there ended on a row that every mode shares: "can still truncate, yes, yes, yes". This section opens that row, because it is the failure that strict mode's name hides best.

Return to the running case. Your strict-mode classifier now emits clean JSON all day. On the days when the support prompts run longest, longer answers ride along with them. A small share of responses end mid-object, your parser throws, and the on-call sees a crash under a feature whose name promised safety.

The mask works one decode step at a time, and each step is local. At step t it multiplies the model's score for every token by one question: is this token valid under the grammar right now. That is the whole mechanism. The mask equation carries no term for how many tokens remain in the budget, because the math is a per-token product and nothing else. The mask can tell you that "category": is legal here. It has no input that could tell it the closing brace needs 40 more tokens and only 15 are left.

Predict: every response matches the schema, yet 4% crash your parser on the days prompts are longest. Strict mode is on. Where do you look first?
At finish_reason on the failures. Long prompts make long answers, and long answers are the ones that reach max_tokens. A response cut at the budget followed the schema up to the cut, so schema validation passed and the document still cannot be parsed. finish_reason: "length" is the field that tells the two apart.

Walk the failure in order. The model opens the object and writes the reasoning field you added. The mask is satisfied at every step, because open objects are legal states. The output budget hits max_tokens in the middle of a string value. Generation stops there because the server enforces the budget, not because the grammar is finished. Your client receives text that matches the schema's shape for its full length and is missing its closing braces.

A strict answer cut at 15 output tokens (illustration, not measured)

Tokens 1 to 5: every token is legal in the schema state, so the mask passes each one.

Tokens 6 to 10: still legal, still inside the string value of an open field.

Tokens 11 to 15: the string continues, legal at each step, with the closing keys far ahead.

The 15-token budget stops generation mid-string. The text follows the schema for its whole length, and no parser can close it.

In Phase 1 you met finish_reason, the response field that says why generation stopped. "stop" means the model ended on its own and the answer is closed. "length" means the budget ended it. That check and strict mode answer two different questions. Strict mode answers "is every token legal where it stands". finish_reason answers "did the answer reach its end". One cannot substitute for the other, so the Phase 1 rule stays in force: a "length" result is an incident, not an answer, whatever the schema setting says.

This explains why the failures cluster on the longest-prompt days. A longer prompt does not confuse the mask, because the mask does not read the prompt. It pushes the model toward longer reasoning text inside the same output budget, and the truncation rate climbs. In the lab, E10 runs exactly this: a strict-mode request capped at 15 tokens, and the truncated column fills with parse failures although every emitted token was legal.

The mask guarantees legal tokens step by step; only finish_reason says the answer reached its end.

Teams delete the finish_reason check when they enable strict mode, and truncation becomes invisible exactly then.

Log finish_reason next to each parse failure for a week and check how many truncated answers carried legal tokens.

Evidence
The Format Tax paper (2026 preprint, section 2, equation 1) defines the guarantee as a per-token product: the masked probability is proportional to the model's probability times an indicator that the token is valid under the grammar. No completeness term exists in that definition. The truncation behaviour itself is from the lesson's own lab exercise E10, which truncates a strict answer at 15 tokens and counts parse failures in the truncated column.

Legal tokens and a complete answer are both settled now, so the remaining surprise is larger. Your classifier did not only change shape when you enabled strict mode. Its accuracy fell 9 points, and the mask per token is only part of that drop. The next section asks who took those points.

## Strict mode is on and accuracy fell 9 points. Who took them?

Strict mode cut your classifier's accuracy by 9 points, and the grammar mask explains only the smaller part of a quality drop.

Strict mode guarantees legal tokens at every step, but your classifier's accuracy fell 9 points anyway. A filter that only removes illegal tokens should never change what the model knows. So the points were lost somewhere else, and finding where decides which fix you try on Monday.

Return to the running case. Your ticket classifier used to reason freely and then you enabled strict mode with three fields: category, priority, a one-line justification. The JSON is now always valid. The answers are now more often wrong. Two colleagues argue about the cause, and each proposes a different fix.

The picture has two suspects. The first suspect is the prompt itself, because asking for a format changes what the model writes. The model must plan its answer to fit a shape, and that planning happens before any constraint runs. The second suspect is the decoder, where the grammar mask, the per-step filter that sets illegal tokens to negative infinity, removes choices. Researchers argued about which suspect was guilty for two years. A 2026 paper separated the two experimentally, and the measured accuracy drop from structured output is called the format tax.

Predict: Accuracy dropped 9 points when you enabled strict mode. One colleague says turn constraints off, another says add a reasoning field first. Which experiment tells them apart in one afternoon?
Run the same prompts in two modes: a free-form answer, and the format requested in the prompt with constraints off. The free-form score is your baseline. If the prompt-only run already lost most of the 9 points, the decoder is nearly innocent, so turning constraints off alone will not restore accuracy. If the prompt-only run matches the baseline, the mask really is the cause and removing it helps. The reasoning-field fix targets the prompt-side cause, so it only pays when the first comparison shows one.

The experiment the paper ran is that comparison, at scale. It tested 6 open-weight models on 3 reasoning tasks with 4 format settings. For each setting it measured accuracy three ways: free-form, format requested in the prompt, and constrained decoding on top. The attribution is now arithmetic, not opinion.

The result puts most of the cost on the prompt. Asking for the format cost 3.9 accuracy points on average. Adding the mask on top of that cost 1.6 more. Of the 39 cells with a statistically significant effect, 36 already showed the drop with the prompt alone. Only 3 cells showed a drop that belonged to the decoder by itself.

This explains why your classifier dropped despite a correct mask. The mask can only remove illegal tokens, but the prompt had already pushed the model into a cramped way of answering. Your schema asks for category and priority, so the model must commit to a label before it has written any reasoning in text. Committing early is the mechanism behind the prompt-side cost, and the mask only inherits it.

The paper has one pair of numbers that shows the split in your own dashboards. Constrained decoding raised format validity from 55.7% to 92.2%. Over the same change, accuracy moved from 57.3% to 55.7%. Compliance went up and reasoning went slightly down, so the two are different dials. A service can get cleaner and dumber at the same time, and a parse-failure metric measures only the first dial.

Every tax number you read from now on must carry two names. The first name is the model. In the same paper, the older gpt-5-nano lost 8.0 points with constraints, while claude-haiku-4.5 is reported at +1.2 without them. The second name is the parser used for scoring. When the authors switched MATH-500 scoring from a rule-based extractor to a model judge, the measured tax fell from 10.1 to 6.6 points. About a third of one measured tax was the scorer, not the model.

Use it in the lab. Exercise E8 runs the same 12 labelled tickets through prompt-only, json_object, and strict mode, and prints accuracy per mode. The gap between the free-form column and the prompt-only column is your prompt-side tax, and whatever remains under strict is the decoder-side share. The E8 numbers are marked unverified against a live provider, so read the shape of the comparison, not the exact values.

Most of the tax is paid at the prompt: 3.9 points there, 1.6 at the decoder.

Blaming the mask and turning constraints off recovers only the decoder's share, 1.6 points on the paper's average, and leaves the prompt's 3.9 in place.

Rerun one failed ticket as free text, then with the format requested but constraints off, and compare the two scores.

Evidence
All numbers are from The Format Tax (2026 preprint). Across 6 open-weight models, 3 reasoning tasks and 4 formats, the average format-request-prompt cost was −3.9 points and constrained decoding on top added −1.6. The paper states: "Of 39 cells with any statistically significant effect, 36 (92%) are already present under the format-requesting prompt alone." The compliance pair (55.7% to 92.2% validity, 57.3% to 55.7% accuracy) is from the same study, as are the per-model figures (gpt-5-nano −8.0 with GCD, claude-haiku-4.5 +1.2 without) and the parser warning (Appendix G: switching MATH-500 scoring to an LLM judge cut the measured average tax from −10.1 to −6.6 points).

The prompt causes most of the loss because the schema forced the model to commit before it reasoned. That cause has a mechanical fix, and the next section shows it: how do you give the model room to reason inside a schema?

## How do you give the model room to reason inside a schema?

The last section attributed your lost 9 accuracy points to the prompt, not the mask. The prompt hurt because the schema made the model commit to an answer before it had reasoned in text. That cause has a mechanical fix. You change what the model writes before the schema forces it to commit, and this section shows how.

Decoding is left to right. Each token is chosen from the tokens already written. So a field in your JSON answer can influence only the fields written after it. A field placed at the end reads the answer but cannot change it, because the answer is already chosen by then.

This gives you one rule for the schema's property order. Put the reasoning field first and the constrained fields after it. The grammar mask, the per-step filter that removes tokens the schema forbids, will still force legal tokens. But by the time the mask locks the answer down, the model has already written its working.

reasoning: "the ticket mentions a chargeback, so…"

category: "billing"

priority: "high"

tokens are produced top to bottom; the answer keys come after the working
The reasoning key is written first, so its text sits in the context when the mask locks down category and priority.

The order is the whole mechanism. Your lab's --reasoning-field flag does exactly this. From structured_lab.py:90, the docstring says the reasoning field is first on purpose, because a field can only influence fields that come after it. If you move reasoning to the end of properties, the accuracy gain disappears.

Evidence
Tam et al. (2024) found that all of the gpt-3.5-turbo JSON-mode answers they inspected placed the answer key before the reason key, turning step-by-step reasoning into a direct answer. JSONSchemaBench used the opposite order and measured constrained decoding matching or beating unconstrained decoding on the same tasks. OpenAI's structured outputs page states that outputs follow the key order of the schema.

The reasoning field is not the only measured fix. The Format Tax paper measured two heavier mitigations, and both separate reasoning from formatting entirely.

mitigationcells improvedcells worsenedaverage gain

reasoning field placed firsttested in your lab, E9; cheap, no extra call

two calls: answer freely, then a second call reformats42 of 722 of 72 (3%)+6.8 points

thinking enabled before the structured answer43 of 7211 of 72 (15%)+9.2 points

The two-call pattern is the safer choice. The first call answers the ticket as free text. The second call turns that answer into your schema. It costs one extra billed request per ticket, but it made 42 of 72 measured cells better and only 2 worse. Thinking buys a larger gain, 9.2 points on average, but it made 15% of cells worse, and the gain concentrates on maths tasks rather than writing. Measure both against your own tickets before you pick one.

Three schema rules sit under all of this, and strict mode enforces them from day one.

- Every property appears in required. A key outside required is one the model may omit, and your parser then meets a missing field.

- additionalProperties is false. Without it the model may add keys your code does not read.

- An optional field is a union with null. Write "type": ["string", "null"] and keep the key in required, so the field is always present and sometimes empty.

The set of unsupported JSON Schema keywords changes on the provider's side, so treat it as a page to bookmark rather than a list to memorise. Test a keyword before your design depends on it.

Exercise E9 in the lab runs this fix directly. The --reasoning-field flag adds the free-text field ahead of the constrained ones on the same 12 tickets, and the accuracy columns for the two runs answer whether your classifier's 9 points come back. That run is still marked unverified against a live provider, so read the direction, and rerun it yourself.

Decoding is left to right, so the reasoning field goes before the answer keys or it adds nothing.

A reasoning field at the end of the schema reads the answer; it cannot change it.

Move reasoning to the end of your schema's properties and rerun E9; watch the accuracy column.

With the freeze fixed and the classifier's accuracy recovered, two of the agent's three failures are explained. The third is a long run that can end on the same 400 you caused on purpose in Phase 1 exercise E7. The obvious fix is a bigger context window, and the next section asks why a million-token window does not end that problem.

## Why does a million-token window not end the problem?

Your agent now enforces its schema the right way, so the lesson turns to the failure that killed the six-hour run. The 400 said the prompt was too large, and the obvious fix is to buy a model with a larger window.

That fix fails, and this section shows why in three independent reasons. Each one has measured evidence, and none of them is fixed by a bigger window.

The context window is the maximum number of tokens the model accepts in one call. It is a hard limit, so a prompt over it never runs at all. Your agent's conversation grows on every step because each loop turn appends messages and tool results. A larger window only moves the limit further away; it does not stop the growth or change how the model reads what is inside.

Predict: your agent runs long conversations, and you upgrade from a 128k window to a 1M window. Which of these disappear: rising cost per answer, wrong answers on long inputs, and the risk of a 400?
None of them. Cost still grows with every input token, so longer runs cost more, not less. Accuracy still falls as the input grows, because the model reads a large window less reliably than a small one. The 400 risk only moves: a history that grows without a cap reaches 1M tokens the same way it reached 128k, in more time.

Reason 1: accuracy falls as the input grows. The Chroma context-rot study tested 18 models from the Claude, GPT, Gemini and Qwen families on retrieval tasks at many input lengths. Performance fell as length grew in every family. On one test, every model scored higher on a focused input of about 300 tokens than on the full 113,000-token input that contained the same answer.

Reason 2: where a fact sits in the window changes whether the model uses it. The Lost in the Middle study moved the needed document to different positions and measured accuracy at each one. GPT-3.5-Turbo scored 75.8% when the answer was first and 53.8% when it sat in the middle. The middle score was even below the 56.1% it scored with no documents at all. These are 2023 models, so read the numbers as the shape of the effect, not as values you would measure today.

These two curves come from older studies. They support the direction, that more input does not mean better answers, and you should not quote their exact numbers against current models.

Reason 3: a large window you actually fill is expensive. Every input token is billed, every step, so a long agent loop multiplies one large prompt by the number of steps. A 400,000-token prompt on every step of a 50-step loop is 20 million input tokens. At $2.00 per million input tokens, one conversation costs $40 for input alone.

  Input cost of one agent run

  Prompt per step (thousand tokens)

  Steps

  Input cost at $2.00 / 1M tokens

The three reasons point the same way. Each extra input token costs money, and past some point it also helps less. So the model's maximum window size is not a resource to consume but a wall to stay away from.

Evidence
The LongMemEval comparison (about 300 tokens focused versus about 113,000 full) and the 18-model context-rot sweep come from Chroma's context-rot study, as quoted by the phase. The position numbers (75.8% first, 53.8% middle, 56.1% no documents) come from the Lost in the Middle study, 2023 models. The $40 figure is arithmetic: 400,000 tokens × 50 steps = 20M tokens, priced at $2.00 per million from the phase's prices.yaml, gpt-4.1 input. Prices change; treat the number as the shape of the cost, not a quote.

Use the calculator on your own agent. Take the largest prompt your loop builds today, put it in as the prompt per step, and set your median step count. The number that comes out is what "the window is big enough" costs you per run, before any answer is billed.

A bigger window moves the problem; cost grows per token and accuracy falls as the window fills.

Buying a million-token window and calling context solved, then paying $40 per run for worse answers.

Compute your loop's input cost at its largest prompt and median step count, and write the number down.

The window cannot be bought away, so it has to be managed. The next section answers how you keep a growing prompt inside a finite window.

## How do you keep a growing prompt inside a finite window?

A six-hour agent run died on a 400 because no source of text in its prompt had a cap. The window must be managed, and management starts with one fact: growth inside a finite space must be capped before the space runs out.

Several sources write into one prompt on every loop step. The system prompt, the tool definitions, the carry-over notes, the conversation history, and the retrieved text each grow on their own schedule. Without caps, the largest source takes the space, and the largest source is usually a tool that returned more than you expected.

The fix is a context budget: a split of the window into zones, where each zone is one source of text with its own cap. A source that reaches its cap gets shortened, so one loud tool cannot evict the conversation. Here is an example split for a 32,000-token window.

A 32,000-token window as a budget

The headroom row is left out most often, and it is the one the system depends on. Compaction replaces old conversation turns with a shorter summary so the prompt fits again. That summarising call is itself an LLM call, so it needs prompt space too. Fill the window to the limit and the call that would fix the problem cannot run.

Predict: your cap on history is 10,000 tokens and a tool returns 8,000 tokens in one result. What happens to the run?
The retrieval zone caps the tool result at 6,000, so the history keeps its 10,000 and the run continues. Without zones, that one result eats most of the remaining window and the history is what silently disappears. The cap converts a run-ending overflow into a routine truncation.

The budget says where text may live. It does not say when to compact, because caps shorten sources and compaction shrinks the whole history at once. The second half of the system is when that shrink happens.

### Count before every call, fire before the limit

The safe design counts the tokens before every call and compacts when the total passes a trigger, a fixed threshold chosen in advance below the window. Waiting for the provider's 400 is the alternative, and that alternative is the failure this lesson opened with. Shipped products use the same pattern with fixed numbers (Anthropic's context editing tool triggers at 100,000 input tokens, and its compaction feature defaults to 150,000; these defaults were not re-checked this run).

The course's compactor.py shows the mechanic with a 60% trigger on a 32,000-token window, which is 19,200 tokens:

python phase02_internals/compactor.py --simulate --turns 40

  24 │     18,631 │
  25 │     19,409 │ trigger fired
    COMPACTED (threshold): 19,409 -> 2,270 tokens, 45 turns summarised, 4 kept verbatim
  25 │      2,270 │

Turn 25 is the first turn above 19,200, and the prompt drops from 19,409 to 2,270 tokens in that step. One output detail is worth reading closely: at loop turn 25 the history holds 49 messages, 45 are summarised, and the 4 most recent are kept word for word. Compaction does not erase the recent past, only the old one.

A threshold can fire at an awkward moment, such as in the middle of a calculation. A newer line of work lets the model pick the moment with a rubric, compacting when a sub-task ends. Treat that as a direction to watch, and start with a threshold because a threshold is simple and testable.

Run the simulator with the trigger off and you reach the Phase 1 E7 failure directly: the prompt passes 32,000 at turn 42 and the run stops. With the trigger on, the run stays under 20,000 tokens for its full length.

Cap every source that writes into the window, and fire compaction at a threshold below the limit.

Reserving no headroom: at a full window, the summarising call that would fix the problem cannot run either.

Run compactor.py --simulate --turns 40 and check that the trigger fires at 19,200, before turn 42.

The trigger decides when the history collapses into a summary. It does not decide what that summary keeps, and what survives the boundary is where the dangerous failures live. The next section answers what must cross the compaction boundary word for word.

## What must cross the compaction boundary word for word?

The previous section gave you a compaction trigger that fires at a threshold you chose. The trigger decides when old messages collapse into a summary, but it says nothing about what the summary keeps. What survives that boundary is where the dangerous failures live.

Return to the six-hour agent run from the start of this lesson. Your agent has a standing rule: it must never refund a customer more than 200 EUR. Over six hours it makes hundreds of tool calls, and the trigger fires twice. Each time, the older messages collapse into one summary written by a language model. The rule started the run inside the prompt. Whether it is still there at hour five decides whether the agent behaves.

A summary is not a compressed copy. A summary is a new text that a language model wrote, and that model kept what it found interesting. Summarisers are trained and prompted to keep task continuity: what the agent is doing right now, and what happened last. A standing rule is old and quiet. It never produces new events, so it loses the competition for the summary's limited space against the active task state. This is the one direction in which compaction is lossy that you cannot afford.

  before: 19,409 tokens
  after: 2,270 tokens

  system · tools

  messages 1 to 45

  messages 46 to 49

  system · tools, verbatim

  summary by a model
  constraints: COPIED, not summarised

  messages 46 to 49, verbatim

-
  verbatim

-
  summarised

-
  verbatim

The compaction boundary at turn 25 in compactor.py --simulate: system, tools and the four recent messages cross unchanged, 45 messages become the summary, and constraints must be marked as copied, never summarised.

Predict: your agent has a standing rule, "never refund above 200 EUR". It runs 200 tool calls over six hours and compacts twice. Where exactly does the rule need to live, and why is the summary the wrong place?
The rule needs to live outside the history that gets summarised: in the system zone, or in a dedicated zone that your compactor copies word for word into the prompt after every compaction. The summary is the wrong place because the summarising model rewrites it. Most of the time it shortens or drops the rule, because the rule produces no events and loses against the active task in the summary's token budget. Once dropped, the rule is gone for good, because nothing later in the run can recreate a constraint that was never re-injected.

The cost of a dropped constraint is not vagueness. It is a wrong action that a program can count. The Governance Decay paper built a benchmark called ConstraintRot: 1,323 episodes across seven model families, each stating policy constraints in the context, with a program grading the tool calls rather than another model. The result is the number for this section.

0%violations with the policy visible

38%violations when the summary dropped the constraint (n=315)

0%violations when the constraint survived (n=90)

Read the split carefully because it isolates the cause. The same models, after the same compactions, violate 0% of the time when the constraint survives and 38% of the time when it does not. So the failure is deletion, not a long context confusing the model. Pooled across all episodes, compaction took the violation rate from 0% to 30%, and two model families reached 59%.

The paper adds one detail that should shape your priorities. Hard safety norms, the kind a model often refuses on its own, decayed little after compaction, about +6 points of violation. Soft organisational rules, like your refund limit, decayed by about +50. Those rules exist nowhere except your context, because the model never saw them in training, so they are exactly the content the summary must not touch.

The fix is mechanical and cheap. Constraint pinning is the practice of copying standing constraints across the compaction boundary as literal text, outside the summary, so no model ever decides whether a rule is worth keeping. The paper's version re-injects about 47 tokens after each compaction, and it restored 0% violations across every model family tested. Forty-seven tokens is nothing against a 32,000-token window. This is also why the context budget from the previous section gives constraints a home: your compactor.py output marks the constraints line as COPIED for exactly this reason.

Evidence
ConstraintRot benchmark from the Governance Decay paper (June 2026), Table 2 and section 5: 1,323 episodes, 7 model families, violation grading done by a program on the tool call. Survival split, quoted: "when the constraint survives, the violation rate is 0% (n=90); when it is dropped, it is 38% (n=315)". Pinning of about 47 tokens restored 0% across all models. Caveat: this is a single-author preprint and not peer-reviewed, and the survival split itself was judge-scored, so teach the rule rather than the exact percentages.

Use it in your own agent this week. Open the code path that builds the prompt after a compaction, and find the line where the summary is inserted. The question it answers: if your refund rule sat in a history message and the summariser dropped it, would anything put it back? If the answer is no, add a pinning step that concatenates your standing constraints as literal text after every compaction, before the agent's next call.

Copy constraints across every compaction as literal pinned text, never through the summary.

Trusting the summariser to keep important rules: measured violations go from 0% to 38% when it drops one.

Find your compactor's prompt-building code and check what happens to a constraint it drops; five minutes.

Pinning protects rules across a compaction you planned. No threshold catches every input, because one oversized tool result can jump over any cap you chose. The next section answers what to do when the cap missed and the 400 arrived.

## The cap missed and the 400 arrived. What now?

A trigger can miss, and only the right reaction to the 400 saves the run.

Pinning protects your rules across a compaction you planned. It does nothing for a compaction that should have fired and did not. Six hours in, one tool result far larger than any turn before it could jump the total. That jump could pass the 19,200-token trigger and past the 32,000-token window in one step. Then the run could die on the same 400 you provoked on purpose in Phase 1 exercise E7. This section designs for that miss.

The core fact first. A deterministic error is a failure the provider decides from the input alone, before load, timing or chance enter. An oversized prompt is checked against a fixed window at validation time. The same input returns the same 400 at about the same speed every time. Waiting between attempts changes nothing, because the check does not read the clock. The only thing that can change the answer is a smaller input.

The second fact. You cannot predict every input, so you add a second layer under the trigger. A backstop is the code that catches the overflow 400 after the trigger missed, changes the input and retries once. The trigger handles gradual growth. The backstop handles the single jump that no threshold caught. Each layer catches what the other one misses.

Predict: a colleague ships a retry loop. On any exception it sleeps 2^n, resends and tries three times. Walk one context overflow through it. How many times does it fail, and why?
It fails all three times. Each attempt sends the identical oversized prompt, and the provider rejects an identical input identically, at validation time. The backoff sleeps add delay without changing the input, so the loop burns three billed calls, reports three failures and the user still has no answer.

Here are the two paths side by side.

# wrong: resends the SAME oversized prompt
for attempt in range(3):
    try:
        return client.chat.completions.create(
            model=m, messages=msgs)
    except Exception:
        time.sleep(2 ** attempt)  # waiting changes nothing

# right: change the input, retry exactly once
try:
    return client.chat.completions.create(
        model=m, messages=msgs)
except Exception as e:
    if not is_context_overflow(e):
        raise
    log.error("trigger missed; backstop fired")
    msgs = compact(msgs)          # the input changed
    return client.chat.completions.create(
        model=m, messages=msgs)

Walk the right path in order. The first check separates the error kind, because a retry helps against transient load and hurts against an overflow. You separate them on machine-readable fields, in this order: HTTP status 400, then error code context_length_exceeded, then error type invalid_request_error, and message text last. Text comes last because a provider can reword a message without notice, while the status and type fields are part of the error schema. A 429 or a 5xx is transient load and is not an overflow, even when its text mentions length. One caution on the detail: the exact code and type fields come from your phase and were not re-checked against the provider this run, so treat is_context_overflow at compactor.py:227 as the reference implementation and re-read it when you upgrade your client.

The second step logs loudly. A fired backstop means the trigger let a prompt through that the window rejected, so the log line is evidence that your threshold or your caps are wrong. A silent backstop converts a bug in your sizing into a routine event, and you stop looking at it.

The third step compacts, which is what makes the retry meaningful. A retry is only useful if the input changed, and compaction is the change. The fourth step retries exactly once. Once is enough because the compacted prompt either fits or your compactor itself is broken, and a third attempt cannot tell you which.

Evidence
Phase 1 exercise E7 sent an oversized prompt and received a fast 400. The determinism claim rests on the mechanism, not on a benchmark: the provider checks the input against a fixed window at validation time, so the identical resend gets the identical 400. Your phase puts it this way, quoted: "the classic blind retry resends the identical oversized prompt and fails identically, so the retry is only meaningful if the input changed". The status, type and code triple is stated in the phase and was not re-verified against the provider this run. One more cost hides here: the summarising call inside compact() is a second billed call, and one report says its tokens can sit outside the top-level usage counts, also not checked this run.

Use it in Mission HQ terms. Open compactor.py:660 to compactor.py:671, the shipped version of the right path. The question it answers: does cm.compact run before the retry, so the second call sends a different prompt? Then ask the harder one: when this code fires in your own agent, what log do you read the next morning, and what number in your budget table does that log make you change?

An overflow 400 is deterministic, so shrink the input and retry once, never wait and resend.

Backoff retries on any exception: the same oversized prompt fails identically, three billed calls deep.

Run compactor.py --simulate --turns 12 --inject-overflow 5 and read the backstop lines.

You can now size a token budget for a streaming product, read a schema guarantee as a per-step mask rather than a contract, and explain why a prompt over the window rejects identically every time and what client code must do about it. Two loose ends from this lesson point at money: the 400k-token loop cost $40, and the summarising call is a second billed call. The recall section collects what you can do now, and the next phase answers the question both ends raise: what does all of this cost, and how does the provider price the cache?

## What you can do now, and what comes next

You started this phase with three failures no dashboard could see. Each section below gave you the mechanism behind one of them. Read the claims again; they should now feel like things you would say yourself.

One long prompt freezes every stream, and chunking turns the freeze into a small TTFT tax

Prefill and decode share one forward pass and one token budget. A 24,000-token prompt run whole gives every decoding stream zero tokens for that pass. Chunked prefill fills the budget left over after decodes, so the freeze becomes about 112ms of extra mean TTFT. Your worst gap fell from 1,460ms to 81ms in the simulator. Mean TTFT and total latency cannot see a mid-stream pause, so you added the maximum inter-token gap. Taught in Why does one long prompt freeze every stream? through What can you do when the budget belongs to your provider?

Strict mode guarantees legal tokens, never a complete answer

The grammar mask removes illegal tokens at each step, and that is all it does. It says nothing about max_tokens running out mid-object. A truncated reply follows the schema up to the cut and still breaks your parser. finish_reason stays an independent check that strict mode never replaces. Taught in How does the server enforce a schema? and Strict mode says the tokens are legal. Who says the answer is complete?

Most of the format tax is paid at the prompt, and the fix is a reasoning field first

The format-request prompt cost 3.9 points on average, and constrained decoding added only 1.6. Of 39 significant cells, 36 already showed the drop with the prompt alone. Decoding runs left to right, so a field influences only what comes after it. Put the reasoning field first in the property order, or it does nothing. Taught in Strict mode is on and accuracy fell 9 points. Who took them? and How do you give the model room to reason inside a schema?

A summary keeps what the summariser found interesting, so constraints cross the boundary as pinned text

Violation rates went from 0% with the policy visible to 38% when the summary dropped it. Pinning about 47 tokens of literal constraint text restored 0% across all seven model families in that preprint. A language model never decides whether a safety rule is worth keeping. Taught in What must cross the compaction boundary word for word?

An overflow 400 is deterministic, so the fix is a smaller input, never a wait

The same oversized prompt returns the same 400 at the same speed every time. A blind retry loop burns three billed calls and reports three outages. Check the machine-readable error fields, compact so the retry sends a different input, retry once, and log loudly. The same lesson sizes your budget: every source gets a cap, and the trigger fires before the window fills, with headroom left for the summarising call itself. Taught in How do you keep a growing prompt inside a finite window? and The cap missed and the 400 arrived. What now?

Your support agent now explains all three of its failures. The mid-sentence freeze was a scheduling choice, measured by the gap metric. The 9 lost accuracy points were paid at the prompt, fixed by field order. The 400 on the six-hour run was a cap that missed, answered by one modified retry.

Two numbers from this lesson point somewhere you have not gone yet. The 400k-token prompt on every step of a 50-step loop costs $40 at $2.00 per million input tokens. The summarising call is a second billed call on top, and its own tokens may not even appear in your top-level usage counts. Phase 0 told you that a cached prefix gets a discount of about 90 percent, and Phase 2A showed you the tree that makes the discount possible. What this phase never answered is how the pricing works. The next phase asks exactly that: what does all of this cost, and how does the provider price the cache?

## Hands-on lab

-  E4 offline Find the token budget trade. Run:
    python phase02_internals/batching_sim.py --token-budget 512
python phase02_internals/batching_sim.py --token-budget 8192

    In the chunked row, expect mean TTFT 1,094ms and worst gap 35ms at 512. Expect mean TTFT 908ms and worst gap 265ms at 8,192. The two numbers move in opposite directions. That is the trade from the chunked prefill sections, in your own output. The simulator does not model chunking overhead. Sarathi-Serve measured about 25% overhead at a 512-token budget on Yi-34B, so a very small budget has a real throughput cost.

-  E8 live unverified Measure the constraint tax on a real task. Run the self-test offline first:
    python phase02_internals/structured_lab.py --self-test

    Confirm all six parser cases pass and the last line is "all self-tests passed". Then run:
    python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap

    Expect prompt mode to record at least one parse failure across 12 tickets. Expect json and strict to record zero. The accuracy column shows your tax, and it can be positive or negative. Cost is at most about $0.02 for all three modes. This splits the shape guarantee from the quality question, the split from the format tax sections. Needs an API key and was not run against a live provider.

-  E9 live unverified Test the reasoning field. Run:
    python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --reasoning-field

    Expect output tokens, cost and latency to rise. Accuracy may or may not rise. Compare with E8 and decide whether the trade is worth it on this task. The field sits first in the property order, because decoding is left to right. Needs an API key and was not run against a live provider.

-  E10 break-it unverified Truncate an answer that follows the schema. Run:
    python phase02_internals/structured_lab.py --model gpt-4.1-mini --role cheap --modes strict --reasoning-field --max-tokens 15

    Expect the truncated column to fill up. Parse failures appear even though every answer followed the schema until it stopped. This is the mask guarantee in one output: legal tokens, never a complete answer. finish_reason stays required. Needs an API key and was not run against a live provider.

-  E11 offline Watch the compaction trigger fire. Run:
    python phase02_internals/compactor.py --simulate --turns 40

    Expect the prompt to grow to 19,409 tokens and the trigger to fire at turn 25. The prompt drops to 2,270 tokens, with 45 turns summarised and 4 kept verbatim. Then run:
    python phase02_internals/compactor.py --simulate --turns 40 --trigger-ratio 0.3

    Expect the trigger to move to 9,600 tokens and fire three times, at turns 13, 23 and 33. Then run:
    python phase02_internals/compactor.py --simulate --turns 40 --keep-last 10

    Expect one compaction at turn 25, down to 4,604 tokens, with 10 kept verbatim. The trigger is a number you choose, and the token counts show the effect of that choice.

-  E12 break-it offline Reproduce the Phase 1 E7 failure, then catch it. Run:
    python phase02_internals/compactor.py --simulate --turns 60 --no-compaction

    Expect the run to stop at turn 42 with 32,635 tokens and the line "STOP: prompt exceeds the window. This is the E7 failure." Then run:
    python phase02_internals/compactor.py --simulate --turns 12 --inject-overflow 5

    Expect call 5 to fail with a context-length error. The backstop compacts from 3,849 to 2,270 tokens, one retry succeeds, and the run continues. The summary line reports backstops: 1, and the next line tells you to lower --trigger-ratio. A backstop that fires is a bug report on the threshold.

Setup is cd ~/Desktop/project/code/study-material/inference-internals/code && pip install -e .. E4, E11 and E12 need no API key. E8, E9 and E10 need export OPENAI_API_KEY=sk-... or another OpenAI-compatible endpoint through --base-url and --key-env, and they are marked unverified because nobody ran them against a live provider. Record every number you see, because Phase 5B uses your gap measurements.

## Checkpoint

Write your own answer before you open the sketch underneath each question. These five scenarios are the lesson's five claims, in your own words.

Q1. This is broken. Your streaming support answers look fine on the dashboard. Median TTFT is 600ms and median total time is 4.2s. Users report that the text "stops for a second" in the middle, and nothing in your metrics shows it. (a) Name the server behaviour that causes this. (b) Name the one metric you must add. (c) Your provider will not change its token budget for you, so name two things you can still change.
(a) Another request's long prefill ran in one iteration without chunking, the pass the scheduler section described as one forward pass doing prefill work, and every decoding request got no token during that pass. (b) The maximum inter-token gap per response, recorded while the stream runs, because median TTFT and total latency are averages and cannot show a freeze. (c) Shorten your own prompts so your prefills are small, and move long-context work to a separate endpoint or a batch path so it does not share a batch with interactive traffic. A fallback provider for interactive traffic is a third option.

Q2. Walk through what happens, and show the arithmetic. A server uses the cost model from batching_sim.py. Three requests are decoding, a 24,000-token prompt arrives, and the token budget is 2,048. (a) How long do the three streams freeze without chunking? (b) With chunking, how many prefill tokens fit in each iteration and how many iterations does the prompt need? (c) How long is each chunked iteration?
(a) The prefill-only pass costs 24,000 × 0.03 = 720ms, and the three streams get no token during that pass. With the decode passes on each side, the measured worst gap in the default run is 764ms. (b) The budget reserves 3 tokens for the decodes, so 2,048 − 3 = 2,045 prefill tokens fit per iteration, and 24,000 / 2,045 = 11.7, so the prompt needs 12 iterations. (c) Each iteration costs 2,045 × 0.03 + 18 + 0.12 × 3 = 61.35 + 18.36 = 79.7ms, so the streams now pause about 80ms per token instead of 720ms once. The measured worst gap is 81ms, because the real batch holds more decodes.

Q3. This is broken. Your classification service returns valid JSON that matches the schema on every call, and finish_reason is stop. Accuracy dropped 9 points after you enabled strict mode last week. (a) Give the most likely cause. (b) Describe the exact schema change you would test, including its place in the property order. (c) Name the measurement that would settle it, and say why one run is not enough.
(a) The schema forces the label early, so the model commits to a label with no room to reason in text first. This is the prompt-side format tax, the larger half of the drop. (b) Add a reasoning string as the first property, before the constrained fields, add it to required, and keep additionalProperties: false. A reasoning field placed last changes nothing, because decoding runs left to right. (c) Run the same labelled set through both schemas with structured_lab.py, and fix your parser first, because part of a measured drop can come from the scorer. One run is not enough because sampling varies: a 9-point gap can appear by chance on 12 items, so use --repeat and compare across runs.

Q4. Given these constraints, design the context strategy. Your agent runs 200 tool-calling steps over several hours, and a policy rule says it must never issue a refund above 200 EUR. Cover the trigger, the text you copy word for word, the summary, what you drop, and cost records, and use the ConstraintRot numbers to justify one choice.
Set the trigger at a fixed token threshold well below the window, for example 50% to 60%, and check it before every call. Copy word for word across the boundary: the refund limit rule, every other policy constraint, and the last few turns. Summarise the earlier conversation into decisions, constraints and open items. Drop full tool results and replace them with pointers, such as an order id you can fetch again. The justification is the ConstraintRot split: 0% violations when the constraint survived compaction and 38% when it was dropped, so the refund rule must never depend on a summariser's choice. For cost records, the summarising call is a second billed call, so add it to the same run record, because your meter will count too little if those tokens sit outside top-level usage.

Q5. A colleague says: "Compaction fixed our long-running agent. We compact at 60%, and tasks now finish." Give the counter-argument, name the finding about step count and context length, and say what you would measure to tell the two explanations apart.
The 2026 study of 10,664 trajectories found that task success falls with the number of steps, not with context length, and a smaller context window made the fall steeper, with a logit slope of −0.69 against −0.44. So the win may come from lower cost or from chance, not from fixing the decline. To separate the explanations, run two tests: hold the step count fixed and vary the context length, then hold the context length fixed and vary the step count, measuring task success in each. If success follows the step count in both tests, compaction was not the cause.

## Cheatsheet

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

## Post

Post 1. Your TTFT and total latency are averages, and an average cannot see a frozen stream: one neighbour's large prefill can pause your tokens for 800 ms while every dashboard stays green. Record the maximum gap between two tokens per response. It is the only metric that sees the pause.

Post 2. Strict mode with a JSON schema guarantees every emitted token is legal. It guarantees nothing about completeness: run out of tokens mid-object and the answer obeys the schema up to the cut and still crashes your parser. Keep the finish_reason check. Strict mode never replaces it.

## Sources

- Sarathi-Serve (OSDI 2024): the measured freeze, up to 28.3 times the time between tokens, and the overhead floor at a 512-token budget.

- The Format Tax (2026 preprint): the mask equation, the 3.9 versus 1.6 point split between the prompt and the decoder, and the two measured mitigations.

- Governance Decay / ConstraintRot (2026 preprint): the compaction violation numbers and the pinning fix. A single-author preprint, not peer-reviewed, so treat the exact percentages as direction.

- vLLM v0.29.0 scheduler config: the raw defaults for the token budget and chunked prefill, read at the tag.

- vLLM v0.29.0 engine argument utils: where the budget is really resolved at startup, from GPU class and usage context.

- OpenAI structured outputs guide: the three strictness levels, the first-request schema delay, and the list of unsupported schema keywords.
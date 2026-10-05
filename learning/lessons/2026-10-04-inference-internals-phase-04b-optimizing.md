Phase 4A left you with a server you started with pinned flags and an operating point you measured yourself: a peak sustained throughput and the TTFT p99 at that concurrency. What it could not tell you is what to do with the three suggestions now in the team chat. One is a checkpoint with its weights stored at 4 bits. One is a flag that stores the KV cache, the attention keys and values the GPU keeps per request, in a smaller number format. One is a method where a small model guesses the next few tokens and the large model checks them. All three are called optimisations. One of them changes the model's weights, and it can degrade open-ended output while every automatic benchmark stays green. One is a slowdown below a context length your users never reach. One provably returns identical output, and it still turns into a slowdown at production load.

So before you apply any of them, you need to answer one question for each: does this change what the model says, or only what the serving costs. A change to what the model says needs a quality gate built from your own traffic. A change to what serving costs needs a load check on your own server. This phase gives you the mechanism behind each of the three suggestions, the one number that decides whether it helps your traffic shape, and the four numbers that answer the question from Phase 4A that is still open: does self-hosting beat the API price for your volume.

This lesson teaches five ideas. They are listed here so you can see where the lesson is going. They will read more clearly once each has been explained below, so come back to this list at the end.

- An accuracy benchmark samples a distribution of tasks, so it can only measure damage where that distribution looks; a quantized model keeps its score wherever damage is smallest and loses it where errors compound. Decide that any quantization gate must be built from his own task, his own languages and his real context length, because no borrowed suite samples them.
- Weight-only 4-bit speeds the memory-bound decode of a quiet server, while weight-plus-activation 8-bit speeds the compute-bound work of a busy one; they are not interchangeable. Pick the format by his traffic shape: W4A16 for low-concurrency latency, W8A8 for throughput under load.
- FP8 KV-cache quantization adds a fixed cost per token while cutting the per-context-token cost, so below a break-even context length it is a regression, and that break-even moves with engine version and GPU. Predict from his users' context distribution whether --kv-cache-dtype fp8 helps or hurts, and distrust any KV benchmark over a year old.
- Speculative decoding only rearranges work the target already does, so its outputs are provably unchanged, its gain saturates while its cost grows linearly in draft length, and it pays only while the verify pass is free. Derive from the structure of the method that it needs a load check rather than an eval gate, that a best draft length exists and is found from measured acceptance, and that rising load can erase the gain entirely.
- Self-host cost per token divides the hourly bill by served tokens, so idle hours multiply it and the comparison is always against one named API's price. Answer the self-host question from structure: name the API being replaced, state a utilisation rather than assume full load, and include the people line, before any rate is argued.

## Where we left the server, and the three suggestions

The rental clock

In Phase 4A you rented one H100 and served a model yourself. The rental clock bills from container start, so the weight download is billed at GPU rates. You finished with a running server and a peak sustained throughput number. You measured it yourself on flags you pinned on purpose.

The operating point

Phase 4A also taught you where capacity lives. The operating point is the peak output tokens per second, plus the TTFT p99 at that same concurrency. Every optimisation in this phase moves that number, so it is the scoreboard the three suggestions are judged on.

Gating a model change

Phase 3B taught you to gate changes that can alter outputs, with a control group and an accuracy budget. A cascade swap and a checkpoint swap share that rule: if the model changes, the gate comes before the launch.

Benchmarks measure one workload

Phase 4A's discipline: a blog's "2x faster" is one configuration on one workload, never the engine. The same discipline applies here, because two of the three suggestions arrive with published numbers attached.

Your team wants the server faster and cheaper. The chat already holds three suggestions: a 4-bit checkpoint, the --kv-cache-dtype fp8 flag, and speculative decoding. Before any method, this phase teaches the one skill that sorts them. Quantization stores a model's weights, and sometimes its activations, in fewer bits than the 16 they were trained in. It rewrites the weights, so it can change what the model outputs. The first suggestion is therefore a model change, and Phase 3B's rule applies: it needs an eval gate. The KV flag changes only the number format of the KV cache. The KV cache is the attention keys and values the GPU keeps per request. It is a precision change too, and it sits in the same group. Speculative decoding lets a cheap draft model propose tokens that the target verifies in one pass. Its paper proves the accepted tokens come from the same distribution as the target alone. It cannot change outputs, and what it needs is not an eval gate but a load check. Two of the three suggestions must pass a quality gate. The third is safe by proof but can become a slowdown under load.

- Does it change the weights or their precision?the 4-bit checkpoint and the FP8 KV flag: yes

- Eval gateyour own task, your real context length, with an interval

- Does it only rearrange work the model already does?speculative decoding: yes, provably

- Load checkmeasure the speedup at your operating point, not at batch 1

This distinction runs the whole phase. The next section opens the first eval-gate item, the 4-bit checkpoint. It starts with a puzzle. One study says FP8 quantization is nearly lossless. Another says human readers find it 16% worse, on the same checkpoints. The question is not who is right, but what each one measured.

## The suite says 99%, the human reader says 16% worse. Who is right?

The published scores cannot be your gate, because a benchmark measures only the tasks it samples.

The orientation sorted the three suggestions by what each one needs. The 4-bit checkpoint changes the model's numbers and needs an eval gate. The FP8 KV flag is a separate decision, with a break-even in context length. Speculative decoding rearranges verification and needs a load check. Before you can gate the 4-bit checkpoint, you need to know why the numbers it ships with cannot do the job.

Your team pastes a link to the checkpoint with a small table. It says recovery, the quantized checkpoint's score as a percentage of the full-precision score on the same suite. The table shows 98.7 to 100.0% on one suite and 96.1 to 98.9% on a harder one. Someone asks if they can ship it today.

what the suite samples
English multiple choice
general knowledge
short, single-step answers

damage here: small

what your users generate
open-ended text
maths and non-Latin scripts
long reasoning, long context

damage concentrates here

A benchmark is a sample of tasks. Each dot is rounding damage, and it lands mostly outside the suite's sample. Illustration, not measured.

A benchmark score is not a property of the checkpoint. It is the average over one particular sample of tasks. Quantization damage is small on short English multiple choice, because the answer survives small rounding errors. Damage concentrates in maths, non-Latin scripts and long reasoning, where each token's error feeds the next token.

Predict: one study says FP8 quantization is nearly lossless, another says human raters judge it much worse. Before calling one wrong, what question would you ask about what each measured?
Ask which tasks each one sampled. The lossless study scored recovery on standard suites, mostly English multiple choice. The second study asked human evaluators to read realistic open-ended prompts, in Japanese. Both numbers are correct for the distribution they sampled. They look in different places, and quantization damage is not spread evenly.

The measured pair, from one study on one 4-bit checkpoint, is the sharpest version of this gap. The recovery range comes from a different study on different models.

1.7%average drop in Japanese, automatic tasks

16.0%drop reported by human evaluators on realistic prompts

96.1–100.0%W4A16 recovery on the standard suites, Llama 3.1, separate study

The two rows are compatible. The mechanism has three parts, and each part explains one digit of the gap.

- Multiple choice absorbs small errors. The model needs only the right option to rank first, so a token-level rounding change often leaves the answer unchanged. Open-ended text has no such buffer. Slightly wrong tokens go directly into the output.

- Errors compound along a chain. In maths and long reasoning, token n's error becomes part of token n+1's input. A small per-token error grows with each step, so long chains degrade first. The study found maths degrades fastest among its tasks.

- Non-Latin scripts sit in the tail. Their tokens and training share are smaller, so rounding affects them more. On human-evaluated Japanese prompts, the drop reached 16.0%, which the automatic tasks did not show.

Standard suites over-weight exactly the first category. Your users generate the second and third. So a 99% recovery table tells you the checkpoint is safe where damage is smallest, and says little about where your traffic lives.

Evidence
Marchisio et al., arXiv 2407.03211, the only study found that ran human evaluation next to automatic metrics on the same quantized checkpoints. The pair is for Command R+ 103B with 4-bit weight-only quantization (W4-g), Tables 3 and 8, not an FP8 checkpoint: "a 1.7% average drop in Japanese across automatic tasks corresponds to a 16.0% drop reported by human evaluators on realistic prompts". The recovery table is from arXiv 2411.02355 ("Give Me BF16 or Give Me Death", Tables 2–3) on Llama 3.1: W4A16 recovery of 98.72, 99.53 and 99.98% across 8B, 70B and 405B on Open LLM Leaderboard V1, and 96.1, 97.4 and 98.9% on V2. The 99.3 to 101.2% range in the same tables belongs to W8A8-FP, not to the 4-bit checkpoint. Both verified 2026-10-04. Newer numbers can replace these; the mechanism, that a suite measures only what it samples, does not change.

One phrase in the chat suggestion names two checkpoints, and both are shorthand. W4A16 means weights stored at 4 bits and activations kept at 16 bits. W8A8 means weights and activations both stored at 8 bits. The format choice is the next section's topic. The gate comes before it, because gating is what decides whether any checkpoint is safe to serve.

The consequence is one rule: build the gate from your own task, your own languages and your real context length. A borrowed suite samples different tasks than your users generate, so it cannot be the gate.

A reasoning model adds a case where accuracy alone misses the regression. A study of compressed reasoning models found up to 52% of failures reach the right answer mid-chain and then wander past it (unconfirmed: from the abstract of arXiv 2606.00206; the table numbers sit in the body). A flipped final answer is not the failure. The chain gets longer and less reliable first, and your token bill and latency move before your accuracy does. So the gate records output length alongside accuracy.

-  E11 offline Run quant_gate.py --self-test, the lab's noise-floor exercise. A 20-item gate from your own task has a detection limit: one flipped item is noise. Which drop in your own 20 items is the smallest this gate can confirm, and what does that gap between 99% recovery and your gate's floor mean for the checkpoint in the chat?

A benchmark measures only the tasks it samples, and quantization damage lives mostly outside the suite's sample.

Shipping on a 99% recovery table assumes damage is spread evenly; human raters measured 16.0% worse where the automatic tasks measured 1.7%.

List your product's five most common request shapes and check which ones any standard suite samples; expect few or zero matches.

The gate decides whether a checkpoint is safe to serve. It does not decide whether that checkpoint makes your server faster, because W4A16 and W8A8 speed up different halves of a request. The next section asks which half your traffic shape needs.

## Which half of a request did you make cheaper?

Picking the right checkpoint means knowing which half of a request your traffic pays for.

The gate from the previous section says whether a checkpoint is safe to serve. It stays silent on speed, because a 4-bit checkpoint and an 8-bit checkpoint make different parts of a request cheaper. Your team pasted a "4-bit checkpoint" into the chat expecting one answer. But the right answer depends on whether your server is quiet or busy.

A request has two phases with different costs. During prefill, the server processes your whole prompt in one pass, and the matrix multiplications dominate the time. During decode, the server writes the answer one token at a time. Each token must read every weight byte from GPU memory. On a quiet server serving one request at a time, decode is limited by memory reads rather than arithmetic. Under heavy load, many requests batch together, the matmuls grow large, and arithmetic becomes the limit instead.

  Decode, quiet server (batch 1)

  read all weight bytes from memory
  math
  Prefill and busy batches (compute-bound)

  matrix multiplications dominate
  W4A16: quarter the blue bar, math unchanged

  W8A8: smaller weights and 8-bit math

Illustration of the mechanism, not measured. Blue is the memory read, grey and orange are arithmetic. W4A16 shrinks the read; W8A8 also shrinks the math.

Weight-only quantization stores the weights at 4 bits but dequantizes them to 16 bits before the matmul. The arithmetic runs exactly as before. This is the W4A16 format from the previous section: W4 means 4-bit weights, A16 means 16-bit activations. It cuts the bytes the GPU must read per token by roughly 4x, so each decode step gets faster. Prefill and large batches gain less, because more of their cost sits in arithmetic that W4A16 leaves at 16 bits.

Predict: you quarter the bytes of every weight but leave activations at 16 bits. Which part of a request gets cheaper, reading the prompt or writing the answer, and at what request rate does the answer change?
Writing the answer gets cheaper, and the preference flips as the request rate rises. Decode reads every weight for each generated token, so cutting weight bytes 4x cuts a real cost there. Reading the prompt is a matmul-bound pass, and 16-bit activations keep that arithmetic at its old cost. As concurrency grows, batches grow, the server becomes compute-bound, and the gain from weight-only quantization shrinks while W8A8 usually gains more.

W8A8 quantizes both the weights and the activations to 8 bits. So the matmuls themselves run in 8-bit integer or floating-point arithmetic. That cheapens the compute-bound work: prefill passes and the large batches of a saturated server. It shrinks weights by only 2x instead of 4x, so it helps a quiet server's decode less than W4A16 does.

The measured split matches the mechanism. Two runs from the same study, same model size:

50.7 → 35.0 ssingle-user 70B code completion, BF16 on 2x A100 → W4A16 on 1x A100

1.4 → 2.4 QPScontinuous batching 70B, BF16 → W8A8-INT, 4x A100

The single-user run is a decode-heavy shape at batch 1, so weight-only 4-bit cut the end-to-end time by 31%, on half the GPUs. W8A8-INT on one A100 took 54.3 s. The saturated run is compute-bound, and weight-plus-activation quantization lifted throughput by 71%. W4A16 on the same setup reached 2.3 QPS, so 4-bit still helped under load, a little less. The paper's average speedup for that setup is 1.87x for W8A8-INT and 1.64x for W4A16. In two other setups, 70B on 4x A6000 and 405B on 16x H100, the two formats tie. The same paper puts it in one sentence. Weight quantization accelerates decode by reducing memory movement, while weight-and-activation quantization improves computational efficiency in prefill. On 405B across 16 H100s, FP8 W8A8 raised docstring-generation throughput from 6.1 to 9.6 QPS, and W4A16 reached 11.1 QPS on the same task.

Evidence
arXiv 2411.02355, "Give Me BF16 or Give Me Death", measured on vLLM 0.6.4.post1 (verified 2026-10-04). Table 5: single-user 70B code completion, BF16 50.7 s on 2x A100, W4A16 35.0 s on 1x A100, W8A8-INT 54.3 s on 1x A100. Table 6: continuous batching 70B code completion on 4x A100, BF16 1.4 QPS, W8A8-INT 2.4 QPS, W4A16 2.3 QPS, with average speedups of 1.87x and 1.64x. 405B on 16x H100, docstring generation, BF16 6.1, FP8 9.6 and W4A16 11.1 QPS. Newer engines may shift the magnitudes; the memory-bound versus compute-bound split is the mechanism and does not expire.

The practical rule follows from the two costs. If your H100 mostly serves a handful of concurrent users with long outputs, decode dominates and W4A16 buys latency. If your Phase 4A measurement showed the server saturating, W8A8 buys throughput. The third case is the quiet trap. At batch 1 with short outputs, the request is over before decode dominates. So quantization mainly saves memory. That is still a valid reason if weights and KV cache no longer fit otherwise.

W4A16 buys decode latency on a quiet server; W8A8 buys throughput on a busy one.

Treating "quantized" as "faster" ships W4A16 onto a saturated server, where the 16-bit arithmetic caps the gain near zero.

Look at your Phase 4A trace: count requests at concurrency 1 versus at peak, and name which format your own shape needs.

Format and speed are now decidable from your traffic shape. What remains is turning a published checkpoint and its recovery table into a SHIP or HOLD decision you can run. The next section answers that.

## Downloading the checkpoint, and the gate that says SHIP or HOLD

You can now read a recovery table, the scores a published checkpoint reports against its full-precision original. What remains is a decision rule you can run: a quantization gate. It is the pass or fail test a checkpoint clears before it replaces the one your server runs. The earlier section showed why no borrowed suite can be the gate. A benchmark measures damage only where its tasks look. Your users live somewhere else, so the gate is your own eval. Its answer is one word, SHIP or HOLD.

The gate has four requirements, and each one traces to a way a checkpoint can fool a lazy test.

- Items from your own traffic. The eval set is drawn from your real task, your languages and your output style. Damage concentrates in maths, non-Latin scripts and long context, so general-knowledge items look where the damage is smallest.

- Prompts at your real maximum context and output length. Two sections back you saw a 3-bit checkpoint lose nearly half its accuracy while writing 4.5 times as much reasoning. A short eval approves a deployment that runs long.

- A paired comparison with an interval. Score both checkpoints on the same items, then estimate the drop with a paired bootstrap: resample the item set many times, re-score both checkpoints on each resample, and take the interval of the difference. Pairing on the same items cancels item difficulty, so the interval measures the checkpoint, not the luck of which items you drew.

- Enough items. The set must be large enough that its noise floor sits below the smallest drop you would act on. The arithmetic below shows why this is a requirement, not a courtesy.

The decision rule itself fits in one tree.

- Does the worst end of the drop interval exceed your maximum acceptable drop?

- yesHOLD: do not ship the new checkpoint, and report the interval

- noSHIP: the damage you could not rule out is within your budget

Predict: your gate reports the drop interval as 0.2 to 3.4 points, and your maximum acceptable drop is 2. SHIP or HOLD?
HOLD, because you judge the interval at its worst end, and 3.4 points is above your 2-point limit. The 0.2 end says the checkpoint might be nearly clean; the 3.4 end says you cannot rule out real damage. A checkpoint shipped on the optimistic end is un-shipped in the incident. The rollback is the expensive version of this same decision.

The last requirement is pure arithmetic. With 20 items, each item is worth 5 points. So one flipped item moves the score by 5 points. That is inside the noise, yet its interval reaches −15%, so a 20-item gate says HOLD on any single disagreement. The paired bootstrap on 20 items convicts a checkpoint only once about four items regress, a drop near 20 points. A 20-item gate is therefore blind to the 2-point drop from the question above. Pick the drop you care about first, then grow the item set until the interval can see it.

Evidence
The gate's shape follows from the sampling argument of Marchisio et al. (arXiv 2407.03211, verified 2026-10-04). Automatic scores and human scores disagreed on the same checkpoints, so only an eval on your distribution settles the question. The 20-item noise figures are the phase's own arithmetic, checked by hand.

You can feel the noise floor without a GPU. Exercise E11 (quant_gate.py --self-test) runs the bootstrap on a synthetic 20-item set. It shows the smallest drop it can convict, before you spend a billed minute. Exercise E12 then runs the same gate live against both endpoints on the rented server.

Only your own eval, at your own context length, can clear a new checkpoint.

Judging the interval at its optimistic end ships the checkpoint the first incident un-ships.

Run E11's self-test and write down the smallest drop your 20 items can convict.

The gate settles the 4-bit checkpoint. The second suggestion in the chat, the --kv-cache-dtype fp8 flag, changes no weight at all. But it carries its own cost model with a hidden threshold. Whether it halves your KV memory or slows your short prompts is the next question.

## The flag that halves KV memory and slows down short prompts

The fp8 flag halves your KV memory, yet below a fixed context length it slows every token you generate.

Weight quantization rewrites the model; the second suggestion in the chat only rewrites a number format. Your team's server stores the KV cache in 16 bits today. That is the attention keys and values the GPU keeps per request. The flag --kv-cache-dtype fp8 stores the same data as FP8 KV cache. That is 8-bit floating point values, so the cache takes half the bytes and reads twice as fast per token. That sounds like free speed, but on short-context traffic it costs speed instead. The flag adds a fixed amount of work to every generated token regardless of context length.

-

-
context length (tokens)
ITL per token

-
BF16: low start, steep rise

-
FP8: higher start, flat rise

break-even
FP8 slower here
FP8 faster here

ITL against context length: BF16 starts lower and rises steeply; FP8 starts higher and rises slowly, so they cross once. Illustration from the vLLM maintainers' fitted lines, not his server.

Predict: an optimisation halves the cost per cached token but adds a constant cost per generated token. Sketch ITL against context length for both variants. Where does each win?
Each variant is a straight line: ITL = intercept + slope × context length. FP8 halves the cached-token cost, so its line rises about half as fast as BF16's. It also adds a fixed cost per token, so its line starts higher on the y-axis. Two lines with different intercepts and slopes cross exactly once. So BF16 wins below the crossing and FP8 wins above it. The crossing point is the whole decision.

The maintainers measured why both parts of the cost model exist, step by step:

- Each decode step reads the whole cache for its context, so halving the bytes halves that read and gives the flatter slope.

- Each decode step also writes new keys and converts the query to FP8 and back, and that work is constant per token regardless of context.

- The write-and-convert work lands as a higher intercept, +0.14 ms per token on the maintainers' H100 setup against BF16.

- At short context the read is a few kilobytes anyway, so the flatter slope saves microseconds while the added intercept costs them back and more.

The break-even context length is the context size where the flatter slope has paid back the higher intercept. It is a property of the engine version and the GPU, not of the technique. The maintainers' own numbers moved it 3.5x between two releases:

SetupBreak-even

Llama-3.1-8B, one H100, FA3, vLLM v0.10.224,889 tokens

Same model and GPU, vLLM v0.19.17,010 tokens

Same model, B200 with FlashInferabout 4,000 tokens

The one number to carry is the crossing, with its conditions in the same breath. They are 7,010 tokens at v0.19.1 on an H100. A team whose median prompt carries 2,000 tokens of context gets slower ITL on every request from this flag. No dashboard panel reports why, because the regression is inside the per-token time, not in any error or capacity metric. A KV-cache benchmark older than your engine version measures a different crossing. v0.10.2's 24,889 and v0.19.1's 7,010 disagree by 3.5x on identical hardware.

Evidence
vLLM maintainers' blog post "FP8 KV Cache" (vllm.ai/blog/2026-04-22-fp8-kvcache), read 2026-10-04: single request, Llama-3.1-8B, one H100, FA3 attention. BF16 decode slope 4.37e-05 ms per token of context, FP8 slope 2.37e-05 (54% of BF16) with +0.14 ms added intercept. Break-even 24,889 tokens at v0.10.2, 7,010 at v0.19.1, about 4,000 on B200 with FlashInfer. A head_dim-256 model (gemma-4-E2B) showed a 1.6x worse TTFT quadratic coefficient under FP8.

The same post carries the quality side of the decision. It is why a short-context eval cannot approve a long-context deployment. On Hopper GPUs an FP32 accumulation bug dropped 128k-token needle-in-a-haystack retrieval from 91% to 13% under FP8. The fix, two-level accumulation, restored 89%, still two points below the BF16 baseline at 128k. At 4k context the same bug was invisible. So a gate run at short context would have passed a checkpoint that loses most long-context retrievals.

Turn the mechanism into a number you can move. The two keepers from the fit: BF16 slope 4.37e-05 ms per context token. FP8 slope 54% of that plus 0.14 ms fixed.

Which side of the crossing are you on?

Your median context (tokens)

Added ITL per token with FP8 at v0.19.1 fit

Verdict

Exercise E13 runs this on the rented server. Serve with --kv-cache-dtype fp8, benchmark short prompts, and watch the regression the flag's name promised against. Then it reverses the context length until the same flag wins. So you measure your own crossing on your own GPU rather than trusting the maintainers' H100 numbers.

FP8 KV halves the per-context-token cost and adds a fixed per-token cost. So it wins only above a break-even context length.

"Half the KV memory is free speed" ships a per-token regression to every short-context user. No standard dashboard names the cause.

Find your traffic's median context length and compare it to 7,010. Below that, the H100 numbers say the flag slows decode.

This section settled the KV flag for decode speed, and the third suggestion in the chat raises a sharper question. Speculative decoding also adds per-token work, but the paper claims it cannot change a single output. The next section asks where that guarantee comes from and why the bet has a published formula.

## A bet with published odds: how speculation works and why it is provably safe

The last two suggestions cost a quality gate or a context threshold. The third, speculative decoding, claims it cannot change a single output, and the whole decision fits in one published formula.

Speculation is the only optimisation here that provably keeps your outputs, so its gate is arithmetic, not evaluation.

Your team pastes "speculative decoding" into the chat next to the 4-bit checkpoint and the FP8 flag. The first two change something: the checkpoint rewrites your model's weights, the flag rewrites its stored context. The third changes only the order in which work the target model already does gets done. That difference decides what kind of answer you owe the team.

Here is the idea. Phase 1 showed that decode speed is limited by memory reads. Each step reads the whole model from GPU memory to produce one token. The arithmetic in the step is cheap by comparison. Speculative decoding spends that cheap arithmetic harder.

- drafta small draft model, a cheap model that guesses the next tokens, proposes k tokens

- verifythe target model scores all k tokens in one forward pass, costing about one normal step

- acceptevery draft token the target agrees with is kept, up to the first disagreement

- replaceat the first disagreement, the target's own token stands; the rest are dropped

The draft length k is how many tokens the draft proposes at once. The acceptance rate is how often the target agrees with a drafted position. Four normal decode steps need four weight reads for four tokens. One speculative round needs roughly one weight read for up to four tokens. This is because verification rides the read the target had to do anyway.

Predict: your draft's per-position acceptance is 0.6, and each draft step costs 10% of a target step. Do you speculate 8 tokens or 2?
A first guess says 8: more tokens proposed, more tokens won. The formula says k=3 wins at about 1.67x. k=8 falls to 1.37x. Each extra position adds the same draft cost but is accepted less often than the one before it. The input that moves the answer most is acceptance rate: at 0.3, k=5 is already slower than no speculation.

Why does a best k exist at all? The paper proves the whole thing as one equation (Theorem 3.8):

                 1 - alpha^(k+1)
improvement = ───────────────────────
               (1 - alpha) (k*c + 1)

alpha = per-position acceptance probability
k     = draft length
c     = cost of one draft step, as a fraction of one target step

Read the two halves separately. The numerator is the expected tokens you win. It rises with k but saturates, because each deeper position survives only if every shallower one did. The denominator is the cost. It grows in a straight line with k, because every drafted position is paid for whether or not it survives. A saturating gain over a rising cost has a peak, and the peak is small.

alphak=1k=2k=3k=4k=5k=6k=8

0.301.181.161.091.020.950.890.79

0.501.361.461.441.381.311.241.11

0.601.451.631.671.651.591.521.37

0.701.551.821.951.981.961.911.78

0.901.732.262.652.933.123.263.40

Speedup computed from the formula, draft cost 0.10; the marked cell in each row is the best k. Read the 0.30 row first: at k=5 the value drops below 1.00, so the "optimisation" is slower than doing nothing. Acceptance rate sets how far right the peak sits, and below about 0.2 there is no gain at any k.

Expected speedup from the formula

Per-position acceptance %
Draft length k
Draft cost per step % of a target step
Speedup

Best k at these settings

Now the safety claim. Appendix A.1 of the same paper proves the accepted tokens are distributed identically to those sampled from the target alone. The argument is short in shape. The target's verify pass computes the probability it assigns each drafted token. Acceptance happens with exactly the probability that would keep the final distribution the target's. So a rejected guess does not bias what comes out; the target's own token replaces it with the right weight. Every token the server returns is one the target would have returned, with the same probability. This is why the correct check before shipping speculation is not your eval suite but a load check. The next section but one covers that check.

The follow-up question your team will ask is why this is the only optimisation in the chat. It is the only one with a proof behind it. Quantization changes the numbers inside the model, so no proof about its outputs is possible. Speculation never touches the target's numbers; it only decides when the target computes them.

"Turn it on, it is a free 2x." Every headline speedup is a batch-1 number. At acceptance 0.3 and k=5 the same mechanism is a 0.95x loss.

"Pick k from measured acceptance, then re-check under load." The formula gives the k; only your server gives the alpha and c to feed it.

Evidence
Leviathan et al., arXiv 2211.17192. Theorem 3.8 is the speedup formula exactly as written above. Appendix A.1 proves accepted tokens are "distributed identically to those sampled from the target alone". The speedup table was recomputed from the formula with draft cost 0.10, matching the phase's script output. The formula, the saturating shape and the output guarantee are structural; they do not age with versions.

Exercise E8 runs this table yourself with python phase04_serving/specdec_math.py and asks where drafting stops paying. One command tries the boundary directly: --best-k --alpha 0.3 --draft-cost 0.2 prints k=1 at 1.08x, and lowering alpha to 0.20 prints 1.00x with the line "Leave it off." So the formula is a decision rule, not just a curve.

Speedup saturates in k while cost grows in k. So a small best draft length exists for any acceptance and draft cost.

Treating it as a free 2x: at acceptance 0.3 a draft of five is already slower than none. Only the formula told you.

Move the acceptance slider in the calc box to 30 and watch the best k collapse to 1.

The formula needs one number from your server, the per-position alpha. The number vLLM actually prints is a different quantity. The next section asks how to convert the server's metric into the formula's input. It also asks what goes wrong when you skip it.

## Your server's acceptance metric is not the formula's alpha

The formula from the last section needs one number, the per-position acceptance alpha. Your server does not print that number, and the gap between what it prints and what you need silently detunes k.

### What the server counts

The situation is your chat after the Red Hat run. Your team enabled speculative decoding with draft length k, the number of tokens the draft proposes per step. The dashboard shows draft_acceptance_rate falling as k rises. One colleague says the draft model is degrading and needs retraining. The draft model is the same in every row.

The vLLM v0.29.0 docs define two counters.

- draft_acceptance_rate is all accepted draft tokens divided by all drafted tokens. It averages over all k positions a step proposes.

- mean_acceptance_length is 1 plus accepted draft tokens divided by verification steps. This is the mean acceptance length, the average tokens kept per verify pass including the bonus token.

Position 1 is accepted with probability alpha, position 2 with alpha squared. Averaging over k positions gives a rate that mathematically must fall as k rises, because each longer k adds one more low-probability position. At alpha 0.6, position 4 lands with probability 0.13 (0.6 to the fourth power) while position 1 lands at 0.6, so the k=4 row averages in 0.13 and the k=2 row does not.

rate = (alpha + alpha^2 + ... + alpha^k) / k

Check alpha = 0.6:  k=2 → 0.48   k=4 → 0.326   k=8 → 0.248
alpha did not move. The average over positions did.

Exercise E9's --from-server mode solves that equation backward, so the server row alone recovers alpha.

Predict: at k=2 your server reports 0.454; at k=4, 0.283. Do you retrain the draft?
The obvious answer is yes, and it is wrong. Row 3 of the table below shows the per-position alpha stayed between 0.555 and 0.577 across all three rows. The draft did not change; only the average lengthened, because the metric divides by more positions as k grows. The correct question is which k wins, not whether the draft broke.

### The falling metric, the flat truth

Red Hat measured one EAGLE-3 draft against gpt-oss-120b on an H200, vLLM 0.13.0, at three draft lengths.

Draft length kReported draft_acceptance_ratePer-position alpha (solved)

20.4540.577

30.3560.567

40.2830.555

The metric fell from 0.454 to 0.283, a drop of 40%. The alpha moved from 0.577 to 0.555, a drop of 4%. One of these rows feeds the speedup formula, and it is not the printed one.

The two choices that follow differ by a third of the gain:

- Feeding the raw k=4 rate of 0.283 into the formula picks k=1, worth about 1.17x.

- Converting to alpha near 0.56 picks k=3, worth about 1.56x on the same server.

Evidence
Red Hat developer article of 2026-04-16, EAGLE-3 draft (nvidia/gpt-oss-120b-Eagle3-v2) on an MXFP4 gpt-oss-120b target, H200, vLLM 0.13.0, GuideLLM 0.5.3: reported rates 45.4%, 35.6% and 28.3% at k=2, 3 and 4. The alphas were solved from rate = (alpha + ... + alpha^k)/k. The vLLM v0.29.0 acceptance-metrics page defines both counters and warns the metrics.speculative_decoding shape "is experimental and its shape may change", so pin the version before a script depends on field names.

The server's acceptance rate averages over k positions, so it falls as k rises while alpha stays flat; solve for alpha.

Reading 0.454 falling to 0.283 as a degrading draft silently detunes k, picking k=1 at 1.17x where k=3 pays 1.56x.

Run E9 (specdec_math.py --from-server) and check the printed alpha against the table's middle row.

A correct alpha and a correct k still assume the verify pass costs nothing. The next section asks what happens to all of this when load makes that assumption false.

## When the free verify pass stops being free

A correct alpha and a correct k still assume the verify pass costs nothing. This section asks what happens when load makes that assumption false.

The same speculative config that gained 1.5x at QPS 1 measured a 1.4x slowdown at high QPS.

Your server in the running case is idle when you test it, and busy at 19:00 when your users arrive. The conversion in the last section sized k on the idle server, where the verify pass really is free. The question now is whether that k survives the busy hour.

### Why the verify pass is free only sometimes

Decode at low concurrency is limited by reading weight bytes from memory, not by arithmetic. One request reads all the weights to produce one token, so the compute units sit mostly idle. Verifying k drafted tokens in one pass reuses the same weight read for k tokens of arithmetic. The idle units absorb that work at no extra time. That is why the verify pass costs about one normal step. The expensive part, the weight read, happens once either way.

Continuous batching, the engine's habit of packing many requests into each step, changes this. At high concurrency the batch already carries enough tokens to keep the compute units busy. It does this with the weight read it was doing anyway. The step is now limited by arithmetic, not memory. Your k verify tokens are no longer free work in idle units. They are extra arithmetic in a queue of real work:

- At batch 1 the verify pass reuses one weight read for k tokens, so it costs about one step.

- At batch 64 the weight read was already shared, so the verify pass adds k times the per-token compute to a step that compute already limits.

- The verify tokens also fail bets: at alpha near 0.5, roughly half the extra arithmetic produces tokens you discard.

So the speedup curve from the formula floats on one condition: the target step stays memory-bound. When load removes that condition, the formula's cost term stops being a constant and the whole curve sinks.

Predict: Staging showed 1.5x at QPS 1 and you shipped. What does the same config measure at high QPS?
It slows down. The vLLM maintainers measured exactly this: Llama3-70B on 4xH100 gained 1.5x at QPS 1. The same configuration measured a 1.4x slowdown on ShareGPT and a 1.8x slowdown on CNN Dailymail at high QPS. Only load changed. Under load the verify tokens cost real compute. The spent-but-discarded draft work arrives on top of the traffic the server was already struggling to serve.

### The crossing is measurable, and the engine already knows about it

The speedup crosses 1.00x at some batch size, and that batch size depends on your hardware, your model and your draft. The EAGLE-3 paper's batch sweep gives the shape on one setup: EAGLE fell from 1.03x to 0.93x between batch 24 and 32, while EAGLE-3 stayed above 1.00x out to batch 56 on the same table. The batch size where it crosses depends on your hardware, so the only check that catches it is a timing run at your real load.

1.5xsame config, QPS 1

0.71xsame config, high QPS (1.4x slowdown)

batch 24–32where EAGLE crossed 1.00x on the paper's table

vLLM exposes the off-switch as configuration: you can set the draft length per batch size. Its example setup reduces speculation as concurrency rises and turns it off entirely above 128 concurrent requests. That is the load check this method needs, instead of an eval gate. It is a benchmark sweep at rising concurrency, and a config that retires the bet when it stops paying.

Evidence
vLLM maintainers' spec-decode post, Llama3-70B on 4xH100: "At high QPS, we see 1.4x slowdown Llama3-70B on ShareGPT with 4xH100, 1.8x slowdown … CNN Dailymail", against 1.5x at QPS 1, same configuration. EAGLE-3 paper (arXiv 2503.01840), Table 5 (caption says A100; the body text says RTX 3090, the paper contradicts itself): EAGLE 1.03x to 0.93x between batch 24 and 32, EAGLE-3 above 1.00x to batch 56, max chain 2, no tree. The per-batch-size draft-length config is vLLM's speculative decoding feature; read both at the versions cited on 2026-10-04.

### What keeps the gain alive under load

The crossing happens later when the target step stays memory-bound at higher batch sizes. Two cases do that, and both matter for the chat suggestions in the running case:

- Long contexts. Each step must also read the KV cache, the attention keys and values kept per request, so a 32k-token context keeps the step memory-bound long after a short one has gone compute-bound.

- Mixture-of-experts models. Each token activates only a slice of the weights, so the step reads many bytes per unit of arithmetic, which is exactly the shape speculation needs. The Red Hat run in the last section held its gains to 200 concurrent requests on an MoE target.

Which raises the last practical question: when you do speculate, which draft do you pick? The rule reduces to one branch. When your output copies from the input, as in retrieval answers, code edits or summarising a pasted document, start with an n-gram draft, a drafter that looks up the last few generated tokens in the prompt and proposes whatever followed them there. It needs no trained model and no extra weights. When the output cannot be found in the input, as in open-ended chat, an n-gram match is rare and acceptance collapses, so the working option is a trained EAGLE-3 head, which costs training time before it saves serving time.

- Does the output copy spans from the input?

- yesn-gram draft: no training, no extra weights, high acceptance on copy-heavy traffic

- notrain EAGLE-3: the largest reported gain on open-ended generation, up to 6.5x in the lab at batch size 1

Speculation pays only while the target step is memory-bound. So a 1.5x idle gain became a 1.4x slowdown when only load changed.

Validating speculation at QPS 1 ships a slowdown for the busy hour. The free verify pass is the first thing load takes away.

Run E10 with --sweep-batch and watch the speedup cross 1.00x. Note the batch size, because that is where your config should turn drafting off.

That finishes the third suggestion: speculation needs a load check, and quantization needed a gate. Both change what the rented server delivers. The next section asks the question underneath all three: does renting the server beat the API at all? It is answered with four numbers.

## Answering the self-host question with four numbers

Self-host cost per token divides the hourly bill by served tokens, so idle hours and the API you compare against decide it.

Every optimisation above changed the tok/s or the quality of the server you rent. None of them answered the question from Phase 4A, whether renting it beats the API at all.

This question arrives in a meeting, usually from someone who has an answer in mind. You have Phase 4A's operating point, the peak sustained tok/s plus the TTFT p99 at that concurrency, measured on your own H100. The mistake is to quote that throughput, divide the GPU's hourly price by it, and say self-hosting wins. That answer assumes full load, which no production server has.

The cost of one served token is the money paid divided by the tokens actually served. Phase 4A's rental clock runs whether requests arrive or not. So the equation has four inputs:

cost per million output tokens =

      hourly rate x number of GPUs
  -------------------------------------------
   sustained tok/s x 3600 x utilisation / 1,000,000

Three of the inputs are arguments. The fourth is a fact about your traffic. Utilisation, the share of paid hours that serve real requests, sits in the denominator and is the input everyone forgets. Halve it and the same hardware produces tokens at twice the price.

-

-
$16/Mtok
$0.8/Mtok
5%
50%
100%
utilisation

-
frontier API, $8.00/Mtok

-
cheap API, $1.60/Mtok

crosses at 10.1% utilisation

crosses at 50.5%
Cost per million output tokens against utilisation, one H100 at $3.49/h sustaining 1,200 output tok/s. The same hardware crosses the two API prices at utilisations five times apart.

Predict: one H100 bills $3.49 an hour and sustains 1,200 output tokens a second. What is your cost per million output tokens, and what one input moves it 10x without touching the GPU or the model?
At full load, $3.49 divided by 4.32 million tokens per hour gives about $0.81 per million tokens. The input that moves it 10x is utilisation: at 10% utilisation the same hardware and the same model cost $8.08 per million. Many comparisons quietly assume 100% utilisation, but nobody actually runs at 100%.

The mechanism has three steps, each one a place the naive answer goes wrong.

- Start from billable time, not from GPU speed. The H100 costs $3.49 an hour whether it decodes or idles, so the output side of the fraction must count served tokens per hour, not capacity per hour.

- Fill in sustained tok/s from your own measurement. Use the operating point you measured in Phase 4A on your model, context length and batch size. A vendor's throughput figure came from a workload that is not yours.

- Apply utilisation, then compare against one named API. Break-even utilisation is the share of paid hours where self-hosting becomes cheaper per token than that API. Replacing a $1.60/Mtok model and replacing an $8.00/Mtok model are two different decisions with the same equation.

  Cost per million output tokens, one H100 at $3.49/h, 1,200 tok/s

  Utilisation
    %
  Your cost /Mtok

Run the sweep instead of anchoring on one row. At 50% utilisation the hardware costs $1.62/Mtok, still 1.01x the cheap API. It turns cheaper than the $1.60 API only above 50.5% utilisation, and cheaper than the $8.00 API above 10.1%. Name the API being replaced before anyone argues about hourly rates.

Then add the line that usually ends the discussion. A deployment needs an owner for upgrades, incidents and the gate from earlier in this phase. A quarter of one engineer is $3,750 a month, about 1.5 times this one-GPU fleet's $2,548 hardware bill. Break-even volume is the monthly traffic where self-hosting pays including the people cost. With the engineer line included, that volume is 3,936 million tokens a month. The fleet's ceiling at 100% utilisation is 3,154 million.

3,154 Mtok/moceiling of this fleet at 100% utilisation

3,936 Mtok/mobreak-even volume vs the cheap API, engineer included

787 Mtok/mobreak-even volume vs the $8.00 API, engineer included

Against the cheap API the break-even volume sits above what the fleet can serve at 1,200 tok/s, so at that throughput no utilisation rescues the comparison. Throughput can rescue it. Break-even needs about 1,498 tok/s averaged over the whole month. A 1.64x lift, about 1,968 tok/s, would break even at about 76% utilisation. Against the $8.00 API the same hardware pays for itself at about a quarter of its capacity. The arithmetic, not efficiency, is deciding in both directions.

Evidence
These numbers are the phase's own worked example: one H100 at $3.49/h (RunPod Secure) sustaining 1,200 output tok/s, run through gpu_economics.py with --role cheap and --role deep, outputs dated 2026-09-17. The arithmetic checks out by hand; the prices and the throughput are dated inputs that will move, while the four-input structure and the engineer line do not. Three published break-even write-ups from 2026 assume throughputs from 620 to about 8,000 tok/s on comparable hardware, a spread over 7x, and reach opposite conclusions (unconfirmed; the sources themselves were not opened). They agree on one point: the answer changes by a factor of about 100 depending only on which API you compare against.

Cost is the easiest input to compute and often the wrong reason to decide. Four considerations sit outside the equation, and any of them can settle the question before arithmetic starts.

- Data control means nothing leaves your network, and for some regulated workloads that ends the discussion.

- A model nobody hosts is yours alone to serve: a fine-tune, a merged model or an open weight with no API.

- The latency floor is yours to control, with no shared queue, no other tenants and no provider incidents.

- Price stability means your cost per token stops moving when a provider rewrites its price list.

The same honesty applies in the other direction. You now own capacity planning, GPU supply, engine upgrades, security patches and the on-call pager.

Use it: run E14 once with gpu_economics.py --gpu-hourly 3.49 --tps 1200 --role cheap and once with --role deep. Write down the pair of break-even utilisations, 50.5% and 10.1% at these inputs, plus the two break-even volumes with the engineer line. Which of the four non-cost reasons applies to your team's model, and does it make the cheap-API comparison irrelevant?

Self-hosting is a bet on utilisation against one named API price, with a people line on top.

Comparing full-load GPU cost per token to the API price: at 10% utilisation the real cost is 10x that figure.

Run E14 with both roles and bring the pair of break-even numbers to the meeting.

You can now gate a model change on your own task with an interval, size a speculative draft from measured acceptance, and bring two break-even numbers to the self-host meeting. The recall section asks you to say the five claims back in your own words.

## What you can do now, and what comes next

You started this phase with three suggestions in a chat. You had no way to tell a model change from a safe rearrangement. Read the five claims again. They should now read like things you would say to a colleague.

- A benchmark is a sampling distribution, not a property of the checkpoint. The same FP8 checkpoint measures 99% recovery on standard suites and 16% worse to human readers, because both numbers are true of different samples. So your gate is built from your own task, your own languages and your real context length, judged at the worst end of a paired bootstrap interval. Taught in The suite says 99%, the human reader says 16% worse and Downloading the checkpoint, and the gate that says SHIP or HOLD.

- Weight-only and weight-plus-activation quantization speed up different halves of a request. W4A16 cuts the weight bytes that limit decode on a quiet server, so it is a latency tool. W8A8 also cheapens the matmuls, so it is a throughput tool under load. Pick by your traffic shape, not by the word "quantized". Taught in Which half of a request did you make cheaper?.

- FP8 KV has a break-even context length, and below it the flag is a silent regression. ITL is an intercept plus a slope, and FP8 lowers the slope while raising the intercept. The crossing moved from 24,889 to 7,010 tokens between two vLLM versions, so an old KV benchmark answers a question nobody asked. Taught in The flag that halves KV memory and slows down short prompts.

- Speculation is provably output-preserving, has a best draft length, and needs a load check rather than an eval gate. The gain saturates in k while the cost grows linearly, so a small best k exists and you find it from measured per-position acceptance. Watch two traps: the server's draft_acceptance_rate falls as k rises even when the true acceptance is flat, and the same configuration that gained 1.5x at low load measures a 1.4x to 1.8x slowdown at high load. Taught in A bet with published odds, Your server's acceptance metric is not the formula's alpha and When the free verify pass stops being free.

- The self-host question is four numbers, with utilisation as the multiplier everyone forgets. Cost per million tokens divides the hourly bill by served tokens, so idle hours multiply the cost, and the comparison is always against one named API's price. Bring both break-even utilisations and both break-even volumes, with the people line, to the meeting. Taught in Answering the self-host question with four numbers.

You can now gate a model change on your own task with an interval. You can size a speculative draft from measured acceptance. You can switch an optimisation off when load makes it a regression. You can also put two break-even numbers in front of the team instead of an opinion.

One assumption in that arithmetic went unexamined all phase. The comparison prices the API as if it can absorb any volume you name. The next phase asks what happens on the client side. The provider you almost replaced caps your rate and ramps your traffic. It asks what your client must do when it does.

## Lab: seven exercises, five offline

Seven exercises exercise five of the six ideas in this phase. Five run offline with no GPU. Each names the claim it proves above it. Where an exercise touches a rented GPU, that is marked. This is because the two live exercises were not themselves verified on one.

-  E8 offline Proves A bet with published odds. Compute the speculative-decoding speedup table from the published formula, (1 − α^(k+1)) / ((1 − α)(k·c + 1)), across acceptance values and draft lengths. What to look for: each row rises to a small best k and then falls, and at acceptance 0.30 the row at k=5 is already 0.95x, a loss. The answer to "where does drafting stop paying" is a number you computed, not a headline.

-  E9 offline Proves Your server's acceptance metric is not the formula's alpha. Run the reader with --from-server on reported metrics and convert with mean_acceptance_length = 1 + k × draft_acceptance_rate to recover the per-position alpha. What to look for: the raw reported rate at k=2, 3, 4 falls (0.454 to 0.283 in the Red Hat numbers) while the converted alpha stays flat (0.555 to 0.577). Feeding the raw rate to the formula picks k=1 at 1.17x; the converted alpha picks k=3 at 1.56x. The vLLM v0.29.0 metrics are marked experimental, so pin the engine version in the script before depending on field names.

-  E10 offline Proves When the free verify pass stops being free. Run the batch sweep with --sweep-batch and watch the speedup curve as concurrency rises. What to look for: the same configuration that shows roughly 1.98x at low load crosses below 1.00x (to about 0.89x in the exercise's numbers) once the verify tokens stop being free. The crossing point, not the peak, is the number you operate against.

-  E11 offline Proves The gate that says SHIP or HOLD. Run quant_gate.py --self-test, no GPU needed. What to look for: what a 20-item eval set can and cannot detect. One flipped item is noise; four regressed items is the smallest drop the set can prove. This is the noise floor that makes the paired bootstrap's worst end the judgement, not its centre.

-  E12 live Exercises The suite says 99%, the human reader says 16% worse end to end. Run the live gate against two endpoints, the BF16 baseline and the quantized checkpoint, on your own task at your real maximum context length, with the interval judged at its worst end. unverified Like every rented-GPU session in this course, prepare the full command file before the rental clock starts; this exercise was not itself verified on a rented GPU.

-  E13 live Proves The flag that halves KV memory and slows down short prompts, by design. Serve with --kv-cache-dtype fp8, benchmark short prompts, and watch the regression nobody warns about. Then reverse it: benchmark long prompts past the break-even context length and watch the flag win. unverified Same note as E12: break it first, then un-break it, because the break-even on your GPU and engine version is not the 7,010 tokens from the blog.

-  E14 offline Proves Answering the self-host question with four numbers. Run gpu_economics.py --role cheap and then gpu_economics.py --role deep, each at both utilisations. What to carry away: two pairs of numbers, break-even utilisation against the $1.60 API and against the $8.00 API, plus the same pair as break-even volumes with the quarter-engineer line included. Those are the numbers you bring to the meeting, in both roles.

The split from Which half of a request did you make cheaper? has no exercise of its own. Nothing in this lab runs one checkpoint at concurrency 1 and again under saturation to watch W4A16 and W8A8 diverge; E12 touches it only at whatever load you happened to use. A closing task would be your Phase 4A client, two checkpoints, two concurrency sweeps, at roughly a dollar of GPU time. Until then, treat the split as an argument, not a measurement.

After the lab, the checkpoint asks you to use all of it under time pressure. You use numbers, in your own words.

## Checkpoint 4B

Six scenarios, each with the numbers you would actually see. Answer in your own words before opening the sketch.

-
The falling metric. Your server runs speculative decoding with draft length 4 and reports draft_acceptance_rate 0.283. At draft length 2 the same server reported 0.454. A teammate says the draft model degrades at longer drafts and wants k set to 1 everywhere. Work out the per-position acceptance at both settings, and say whether the teammate is right.

Answer sketch
Convert with the identity: mean acceptance length = 1 + k × rate. k=2 gives 1.91, k=4 gives 2.13. The implied per-position acceptance is 0.555 to 0.577 at both settings, so the draft is flat; the reported rate falls with k because the server's metric averages over drafted positions and later positions accept less often, not because the model got worse. Given the true alpha lands near 0.56, the formula's best k is around 3 at roughly 1.56x, while the teammate's k=1 gives about 1.17x. Reading the raw rate instead of the per-position alpha silently detunes the setting it was meant to tune.

-
Staging says yes, production says no. You validated speculative decoding in staging: 1.5x at QPS 1, on Llama-3-70B with four H100s. In production, serving ShareGPT-like traffic at high QPS, the same configuration runs 1.4x slower. What explains the reversal, and what one configuration change defends you without losing the idle gain?

Answer sketch
At QPS 1 the target's step is limited by memory reads, so the verify pass rides a step that was already paid. Under production load the batch makes each step compute-bound, so the extra verify tokens cost real compute and the speedup crosses 1.00x. The maintainers measured exactly this: the same configuration at 1.5x at QPS 1 slowed 1.4x on ShareGPT and 1.8x on CNN/DailyMail at high QPS. The defence is the per-batch-size draft length configuration in vLLM, which sets k per concurrent-request band and turns speculation off above a threshold like 128 concurrent requests. The question to ask after any speculation change is whether your step is still memory-bound, which is a load check, not an evaluation.

-
Two GPUs, one month. You rent two H100s at $3.49 an hour each, each sustaining 1,200 output tokens a second. Your measured utilisation is 30%. Compute your cost per million output tokens for the month (730 hours), and say which API the fleet replaces: the $1.60 one or the $8.00 one.

Answer sketch
The monthly bill is 2 × $3.49 × 730 = $5,095. Served volume is 2,400 tok/s × 3,600 s × 730 h × 0.30, about 1,892 million tokens. Cost per million is $5,095 / 1,892, about $2.69. So this fleet beats the $8.00 API and loses to the $1.60 API, before any operator time. The same hardware at 100% utilisation would land at $0.81 per million and beat both, which is why utilisation, not the hourly rate, is the number to argue about in the meeting.

-
The gate that passed. Your 20-item gate ships a 3-bit quantization of a small reasoning model. Every item produced short chains, and accuracy held. In week two, users on long problems report wrong answers, and a rerun of the gate at your real maximum output length shows accuracy collapsed. What was wrong with the gate, given the checkpoint was unchanged?

Answer sketch
An accuracy suite measures only what it samples. Damage from quantization concentrates where token-level errors compound, and a long reasoning chain gives errors more positions to compound in, so a model can keep its score at 5,000-token outputs and lose its accuracy at 20,000-plus. Your gate sampled only short generations, so it never looked where the damage lives. A gate for a reasoning model needs items at the real maximum output length, not representative short ones. No re-run with more short items fixes this, because the failing region was outside the sample, not inside the noise floor.

-
The proposal on one number. A colleague sends the self-host proposal: "our H100 at 1,200 tok/s gives $0.81 per million output tokens, the API charges $1.60, self-hosting wins." List what the proposal is missing before you would sign it.

Answer sketch
Four things, each a number or a name. First, utilisation: $0.81 assumes 100%, and at 10% the same hardware costs $8.08 per million, so state the measured figure. Second, the named API being replaced: against a $1.60 API the break-even utilisation is 50.5%, against an $8.00 API it is 10.1%, and "the API" without a name hides which decision you are taking. Third, the people line: a quarter-engineer at $3,750 a month on a one-GPU fleet pushes the break-even volume to about 3,936 million tokens a month, above the fleet's ceiling of about 3,154 at 1,200 tok/s, so at that throughput the comparison cannot break even. Only about 1,498 tok/s or more, averaged over the month, would rescue it. Fourth, the throughput input: it must come from your own Phase 4A operating-point measurement, because published write-ups disagree on it by more than 7x. A proposal with all four is arithmetic; without them it is an opinion.

-
The audited result. An audited benchmark publishes: engine B, 2x faster than engine A, and the audit confirms the submitter followed the rules. Your manager asks whether you should switch. What do you check before answering, and why is "B won" not an answer?

Answer sketch
Phase 4A's discipline applies: an audit verifies that the rules were followed, not that the configuration represents your workload. Check the model, the GPU, every pinned flag including the quantization path, the prompt and output lengths, and the concurrency. Winners have flipped when only the quantization path changed, so a result measured on a different path is a result about a different server. The unit of the claim is one configuration on one workload, never the engine. The audit tells you the number is honest; it does not tell you the number is yours. The answer to the manager is a decision about whether your own experiment is worth the GPU hours, and that decision needs no winner picked from the table.

If a question cost you a guess, go back to the section it came from: q1 and q2 to the speculation sections, q3 and q5 to the four-number arithmetic, q4 to the gate, and q6 to Phase 4A's benchmarking discipline. After this, the cheatsheet condenses the whole part onto one screen.

## Cheatsheet — part B

QUANTIZATION FORMATS — pick by traffic shape, and download, don't quantize
  FP8 W8A8    weights+activations  ~2x smaller   Ada/Hopper/Blackwell, AMD
  INT8 W8A8   weights+activations  ~2x           Turing onward, plus CPU
  AWQ W4A16   weights only         ~75% off      Turing–Hopper, NOT AMD GPU
  GPTQ W4A16  weights only         ~75% off      Volta onward
  AutoAWQ is DEPRECATED (v0.29.0 docs); tooling moved to llm-compressor
  a pre-quantized checkpoint is detected from its config;
    --quantization is for ONLINE quantization only

  W4A16 speeds DECODE (reads fewer weight bytes)  -> low concurrency
      70B single user: 50.7 s (BF16, 2x A100) -> 35.0 s (W4A16, 1x A100)
  W8A8 speeds decode AND prefill (matmuls too)    -> under load
      70B batched, 4x A100:  1.4 -> 2.4 QPS (W4A16 reached 2.3)
  batch 1 + short outputs -> quantization saves memory, not time

QUALITY — a suite samples a distribution; yours is different
  automatic metrics -1.7% | human raters -16.0% — same checkpoint (Command R+ 103B, W4-g)
  damage concentrates: maths/reasoning > non-Latin > long context
  reasoning model, 3-bit:  85.6% at 5,200 tok -> 47.0% at 23,400 tok
    put OUTPUT LENGTH in the gate; no standard suite reports it

KV CACHE FLAG — halves KV, has a break-even context length
  --kv-cache-dtype fp8 : slope 54% of BF16, +0.14 ms per token (8B, H100)
  break-even 24,889 tok @ v0.10.2 | 7,010 tok @ v0.19.1 | ~4k on B200
  BELOW the break-even it is SLOWER, and nothing warns you
  head_dim 256: 1.6x TTFT regression
  precision bug: 128k retrieval 91% -> 13%, two-level fix -> 89%
  any KV benchmark over a year old is out of date

THE GATE — four requirements, judged on the worst end of the interval
  >=99% general suite | >=98% on YOUR task suite
  + long-context eval at your REAL maximum | + throughput run
  20 items: 1 flip -> interval [-15%, 0%]; smallest clear drop = 4 of 20
  noise that is NOT a win: FP8 100.8% maths; 0.933 vs 0.930 (half a problem)

SPECULATIVE DECODING — provably same output; needs a load check, no gate
  speedup = (1 - a^(k+1)) / ((1 - a)(k*c + 1))      Theorem 3.8
    a = per-position acceptance | k = draft length | c = draft cost ratio
    numerator saturates, denominator grows linearly -> a best k exists,
    and at a=0.30, k=5 is already 0.95x: a loss with speculation ON
  SERVER METRIC TRAP:  mean_acceptance_length = 1 + k * draft_acceptance_rate
    reported rate falls 0.454 -> 0.283 as k rises; true alpha 0.555–0.577
    --alpha 0.283 -> k=1 (1.17x) | --alpha 0.555 -> k=3 (1.56x)
  methods: n-gram (zero setup) | EAGLE-3 (days of training)
    START WITH N-GRAM when the output copies from the input
  load erases it: same config 1.5x gain @ QPS 1, 1.4x/1.8x SLOWDOWN high QPS
    EAGLE below 1.00x between batch 24 and 32
    --num_speculative_tokens_per_batch_size turns it off above a threshold
  the real question is not "is batch high" but "is the target still
    memory-bound": long context and MoE stay memory-bound far longer

SELF-HOST — four inputs, answer against ONE named API
  $/Mtok = (hourly x gpus) / (tok_s x 3600 x utilisation / 1e6)
  MEASURE tok/s yourself; it is the only input you cannot look up
  utilisation is a multiplier: idle hours are billed hours
  1 H100, $3.49/h, 1,200 tok/s:  $0.81/Mtok @100% | $8.08 @10%
  break-even 50.5% util vs $1.60 API | 10.1% vs $8.00 API
  + quarter-engineer $3,750/mo (~1.5x the hardware):
      vs cheap API the fleet's ceiling (3,154M tok/mo) sits BELOW its
      break-even volume (3,936M) at 1,200 tok/s; needs ~1,498 tok/s averaged over the month
  overrides outside the arithmetic: data control, a model nobody hosts,
    a latency floor you own, price stability

COMMANDS
  specdec_math.py                          speedup table, offline
  specdec_math.py --from-server            convert the server-reported rate
  specdec_math.py --sweep-batch            find where it becomes a loss
  specdec_math.py --best-k --alpha X       optimal draft length
  quant_gate.py --self-test                the noise floor, offline
  quant_gate.py --baseline-url ... --candidate-url ...   the live gate
  gpu_economics.py --gpu-hourly X --tps Y --role cheap   then --role deep

## Posts

Two lines from this phase are ready to post. Each carries one claim, and each comes with the number you measured or read yourself.

The suite and the human reader

"Same quantized checkpoint, two verdicts: automatic tasks dropped 1.7% while human evaluators on realistic prompts said 16% worse. Both are right, because a benchmark only measures the tasks it samples. Gate on your own task."

The claim becomes yours after you run the gate in E12 on a rented GPU, so post it only then. The advice at the end is then a rule you have used, not a quote.

The maintainers' own slowdown

"The vLLM team measured speculative decoding at 1.5x faster with one request per second. Then they measured the same configuration at 1.4x slower under load. Nothing in the config changed. Only the load did. A free-verify optimisation needs a load check, not just an idle benchmark."

The claim becomes yours once you run E10 and watch 1.98x become 0.89x in the batch sweep, so post it after that.

Quality drop on the same quantized checkpoints, from arXiv 2407.03211: the study that ran human evaluation next to automatic metrics.

Post the first when the team quotes a recovery table. Post the second when someone wants speculative decoding on by default.

## Sources

Each source below says what this lesson took from it. Everything was fetched and checked on 2026-10-04, at the versions named.

- "Give Me BF16 or Give Me Death"? — https://arxiv.org/abs/2411.02355 — the recovery tables that show near-lossless scores on the standard suites, plus the serving split: W4A16 at 35.0 s single-user on one A100 against BF16 at 50.7 s on two, and W8A8-INT at 2.4 QPS against W4A16 at 2.3 QPS under continuous batching, measured on vLLM 0.6.4.post1.

- How Does Quantization Affect Multilingual LLMs? — https://arxiv.org/abs/2407.03211 — the human-evaluation correction: the −1.7% automatic drop against the −16.0% human drop on the same 4-bit Command R+ 103B checkpoint, in Japanese.

- Fast Inference from Transformers via Speculative Decoding — https://arxiv.org/abs/2211.17192 — Theorem 3.8 with the speedup formula, and Appendix A.1 proving accepted tokens come from the target's own distribution.

- EAGLE-3 — https://arxiv.org/abs/2503.01840 — the batch-size table where the speedup crosses below 1.00x as load rises, the pattern behind the load check.

- Quantized Reasoning Models Think They Need to Think Longer — https://arxiv.org/abs/2606.00206 — the effect that connects low-bit quantization to longer, wronger reasoning. Read from the abstract; the specific table numbers were not verified this run.

- The State of FP8 KV-Cache in vLLM — https://vllm.ai/blog/2026-04-22-fp8-kvcache — slope, intercept and break-even tables (24,889 to 7,010 tokens between two versions), the 91% to 13% accumulation bug, and the B200 break-even of about 4k.

- Speculative decoding slowdown, by the maintainers — https://vllm.ai/blog/2024-10-17-spec-decode — 1.5x faster at QPS 1, then 1.4x and 1.8x slower at high QPS, on the same configuration.

- vLLM v0.29.0: speculative decoding acceptance metrics — https://docs.vllm.ai/en/v0.29.0/features/speculative_decoding/acceptance_metrics/ — the definitions of draft_acceptance_rate and mean_acceptance_length, and the experimental-status warning.

- vLLM v0.29.0: AutoAWQ quantization — https://docs.vllm.ai/en/v0.29.0/features/quantization/auto_awq/ — the deprecation notice sending new quantization work to llm-compressor.

- Red Hat: speculative decoding for gpt-oss — https://developers.redhat.com/articles/2026/04/16/performance-improvements-speculative-decoding-vllm-gpt-oss — the acceptance rates 0.454, 0.356 and 0.283 at k of 2, 3 and 4 that show the server metric falling while per-position alpha stays flat.

- Your own phases — Phase 4A, where the peak sustained throughput number you measured in this lesson's economics comes from, and Phase 5A, where the API side of that comparison gets its rate limits.

One note on dates: the break-even numbers, serving figures and metric definitions above are properties of the versions named beside them. A newer engine moves the numbers; the claims in this phase do not move with them.
# Phase 4B — Making it faster, and deciding whether to do it at all

Part A got a server running and measured it. This part is about the two levers that change those numbers, and then about the decision the whole phase exists to answer.

The two levers behave very differently, and the difference is worth stating before either section.

**Quantization changes your model.** It is a weight change, so it can change your outputs, and it needs an evaluation gate.

**Speculative decoding does not change your model.** The original paper proves the output is drawn from the same distribution as the unaccelerated model. It needs no gate. What it needs is a check that it is still helping, because its benefit can turn negative purely because your traffic went up.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  4.4  Quantization             — what it buys, and what it quietly costs │
│  4.5  Speculative decoding     — a bet with published odds               │
│  4.6  The self-host decision   — arithmetic, not preference              │
└──────────────────────────────────────────────────────────────────────────┘
```

Part A is a prerequisite. Section 4.6 needs the throughput number you measured there.

Time: 2 to 3 hours. Five of the seven exercises are offline. Budget about $2 to $3 of rented GPU for the other two.

---

---

## 4.4 — Quantization (what it buys, and what it quietly costs)

Why this matters: quantization is the single biggest lever on the cost table you built in 4.1. It halves or quarters the memory a model needs, which raises the concurrency Phase 2 taught you to care about. It is also a change to your model's weights, which makes it a model change, which means Phase 3B's rule applies: it needs a gate.

**The one-line summary.** Quantization stores weights, and sometimes activations, in fewer bits. Fewer bits means fewer bytes moved from GPU memory per decode step, and Phase 1 told you decode is memory-bound. So it usually makes things faster as well as smaller.

### The formats that matter

```
┌──────────┬──────────────────────┬────────────┬───────────────────────────┐
│ format   │ what it quantizes    │ memory     │ hardware it needs         │
├──────────┼──────────────────────┼────────────┼───────────────────────────┤
│ FP8      │ weights + activations│ 2x smaller │ Ada, Hopper, Blackwell,   │
│ W8A8     │                      │            │ and AMD                   │
│ INT8     │ weights + activations│ ~2x        │ Turing onward, plus CPU   │
│ W8A8     │                      │            │                           │
│ AWQ      │ weights only         │ ~75% off   │ Turing to Hopper, Intel   │
│ W4A16    │                      │ the weights│ GPU, x86 CPU. NOT AMD GPU │
│ GPTQ     │ weights only         │ ~75% off   │ Volta onward              │
│ W4A16    │                      │ the weights│                           │
│ NVFP4    │ weights, sometimes   │ 3.5x vs    │ Blackwell only            │
│          │ activations too      │ FP16       │                           │
│ MXFP4    │ MoE expert weights   │ 4.25 bits  │ Blackwell, AMD ROCm,      │
│          │                      │ per param  │ Hopper through Triton     │
└──────────┴──────────────────────┴────────────┴───────────────────────────┘
```

Two changes since older material was written, both verified in the engines' source on 2026-09-13.

**AutoAWQ is deprecated.** vLLM's own page says the functionality moved into `llm-compressor`. AWQ checkpoints still load. The AWQ tooling is dead. Any guide telling you to run AutoAWQ is out of date.

**The 4-bit tier is now NVFP4 and MXFP4, not INT4.** MXFP4 arrived as a shipped weight format rather than a step you perform: the gpt-oss models were released with their expert weights already in MXFP4.

### You probably will not quantize anything yourself

This surprises people who expect a conversion step. In 2026 the normal path is to download a checkpoint someone already quantized. One vendor organisation alone publishes 773 such models, with new ones appearing within days of a base model release.

And here is the part that causes real confusion when you first serve one:

**`--quantization` is for ONLINE quantization, applied as the model loads.** When you serve a checkpoint that is already quantized, both engines read the method out of the checkpoint's own config and you do not pass the flag at all. SGLang's documentation states it directly: for an offline-quantized model there is no need to add the argument.

So the decision is usually "which published checkpoint", not "which algorithm".

**Prefer a checkpoint whose publisher shipped its accuracy table and the exact command that produced it.** A quantized checkpoint with no published recovery numbers is an unevaluated artifact, whoever uploaded it.

### What it costs in quality: two studies that appear to disagree

This is the most important part of the section, and the honest answer takes both studies.

**The optimistic result.** A 2024 study, revised in May 2026, ran over 500,000 evaluations across the whole Llama-3.1 family. Accuracy recovery against the BF16 original:

```
                        8B       70B      405B
  W8A8-FP  (OpenLLM v1)  99.3%    99.7%   100.1%
  W4A16    (OpenLLM v1)  98.7%    99.5%   100.0%
  W8A8-FP  (OpenLLM v2) 101.2%   100.0%    99.9%
  W4A16    (OpenLLM v2)  96.1%    97.4%    98.9%   ← read this row
```

Two things to take from it. FP8 is close to lossless at every size. And 4-bit recovery improves with model size, 96.1% to 97.4% to 98.9%, but only on the harder benchmark suite. On the easier suite every cell is above 98.7% and the size effect disappears entirely.

**The pessimistic result.** A study by a different group ran human evaluation alongside automatic benchmarks on the same quantized checkpoints. Its central finding, quoted:

> automatic evaluations estimate performance deterioration relative to FP16 across tasks at −0.3% (French) and −1.7% (Japanese) vs −16.6% and −16.0% reported by human evaluators.

Automatic metrics said 1.7% worse. Humans said 16% worse. On the same model.

**These do not contradict each other, and the reason is the lesson.** The first study measures mostly English multiple-choice benchmarks. The second measures open-ended generation in several languages, scored by people.

> The same checkpoint can be 99% recovered on a multiple-choice suite and 16% worse to a human reader.

Where the damage concentrates, ranked by measured evidence:

1. **Maths and multi-step reasoning.** On a multilingual maths benchmark at 4-bit, one 35B model lost 13.1% on average and 17.3% in Chinese.
2. **Non-Latin scripts.** Latin-script tasks lost 0.7% where non-Latin lost 1.9% on the same model.
3. **Long context.** See the KV cache section below, and note the RULER result further down.
4. General knowledge, which is where the standard suites look, and where the drop is smallest.

### What it buys in speed, and the split nobody explains

Quantization does not make everything faster. Which part gets faster depends on which part you quantized.

```
  WEIGHT-ONLY (W4A16)              WEIGHT AND ACTIVATION (W8A8)
  fewer weight BYTES to move       fewer bytes AND real low-precision
  helps the memory-bound part      matrix multiply
       ↓                                ↓
  DECODE gets faster               DECODE and PREFILL get faster
       ↓                                ↓
  wins at LOW concurrency          wins under LOAD
  (one user waiting on tokens)     (a busy server)
```

Measured, on the same paper's serving benchmarks:

- One user, 70B on an A100: BF16 took 50.7 seconds, W4A16 took 35.0 seconds. That is 1.45x.
- Under continuous batching, 70B on an A100: BF16 served 1.4 queries per second, W8A8 served 2.4. That is 1.87x.
- Under load, 405B on H100s: 6.1 to 9.6 queries per second with W8A8, which is 1.57x.

**The practical rule.** Low traffic and latency-sensitive: 4-bit weight-only buys you latency. High traffic: 8-bit weight-and-activation buys you throughput. Batch size one with short outputs: quantization mostly buys you memory and little else.

### KV cache quantization is a separate decision with a threshold

Phase 2 showed the KV cache dominates GPU memory at high concurrency. You can quantize it too, with `--kv-cache-dtype fp8` on both engines. It halves KV storage.

It also has a break-even in context length, and below that threshold **it makes things slower**. From the vLLM maintainers' own measurements on an H100 at concurrency 1:

```
┌──────────────────────────┬───────────────────┬──────────────────────┐
│ model                    │ FP8 decode cost   │ break-even context   │
├──────────────────────────┼───────────────────┼──────────────────────┤
│ Llama-3.1-8B             │ 54% of BF16       │ about 7,000 tokens   │
│ gpt-oss-20b              │ 80% of BF16       │ about 22,000 tokens  │
│ gpt-oss-20b, skipping    │ 71% of BF16       │ about 7,700 tokens   │
│ sliding-window layers    │                   │                      │
│ Gemma-4-E2B, head_dim 256│ 68% of BF16       │ TTFT gets 1.6x WORSE │
└──────────────────────────┴───────────────────┴──────────────────────┘
```

Under load with about 20,000 input tokens, the same 8B model went from 450 to 518 output tokens per second, a 14.9% gain, with median inter-token latency falling 14.8%.

**Three warnings from that same source, all worth more than the speedup.**

First, do not enable it below roughly 7,000 tokens of context. The fixed overhead makes BF16 faster.

Second, one model shape gets worse rather than better. A head dimension of 256 with prefill-heavy traffic produced a 1.6x TTFT regression.

Third, and this is the one to remember: a precision bug in attention accumulation once took a 128,000-token retrieval task from **91% accuracy to 13%**. It was invisible at short context and catastrophic at long context. It is fixed, and it is the cleanest example of why a short-context eval cannot clear a long-context deployment.

One more fact that invalidates most of what you will read: between two engine versions, the break-even for that 8B model moved from 24,889 tokens down to 7,010. **Any KV cache benchmark more than about a year old is worthless.**

### The failure mode that an accuracy gate cannot see

A 2026 study quantized reasoning models and measured their output length as well as their accuracy. On a maths benchmark, one 1.5B reasoning model went from:

```
  BF16       85.6% accuracy    5,200 tokens of reasoning
  AWQ 3-bit  47.0% accuracy   23,400 tokens of reasoning   ← 4.5x longer
```

Accuracy nearly halved, and the model burned four and a half times the output tokens to get there. **The memory you saved is repaid, with interest, in decode time and in output-token cost.**

The mechanism is specific. In up to 52% of failures under aggressive quantization, the model reached the correct answer in an intermediate step and then failed to commit to it. At uncertain token positions the quantized model over-produces hedging words. A simple penalty on those words cut reasoning length by 12% to 23% without hurting accuracy.

State the conditions honestly: 3-bit on a 1.5B model is the far end of aggressive, and this is not what happens at 4-bit on a 70B. But the lesson generalises. **If you serve a reasoning model, put output length in your gate, not just accuracy.** No standard benchmark reports it.

There is a second effect with weaker evidence. One small study of tool calling found that model family predicted quantization tolerance better than parameter count, and that easy benchmark tiers hid a cliff: on parallel and multi-tool calls, the schema-validity drop was about five times larger than on simple calls. Treat the magnitudes as untransferable, because that study used small models and a different quantization family. Treat the shape as a warning: test the hard tier of whatever your agents actually do.

### The gate

Phase 3B gave you the discipline. Here is the quantization-specific version, and `quant_gate.py` implements it.

```
python phase04_serving/quant_gate.py --self-test
python phase04_serving/quant_gate.py \
    --baseline-url http://localhost:8000/v1  --baseline-model <fp16-id> \
    --candidate-url http://localhost:8001/v1 --candidate-model <fp8-id> \
    --max-drop 0.02
```

It sends one labeled set to both endpoints, reports both accuracies and both throughputs, and gives a delta with a 95% interval from paired bootstrap resampling. The verdict uses the **worst end** of the interval, not the midpoint, because a gate that rounds in your favour is not a gate.

**Why the interval is not optional.** Look at three published quantization results:

- A 4-bit model scored **higher** than its baseline on an AIME benchmark.
- An FP8 model scored 100.8% recovery on a maths benchmark.
- A quantized coding model scored 0.933 against the original's 0.930 on a 164-problem benchmark, which is a difference of about half a problem.

None of those means quantization improved the model. They are measurement noise, and a gate without a tolerance band will happily report them as wins. The same noise in the other direction will report a phantom regression.

**What a published gate looks like.** One vendor's model card ships the recipe, the baseline score, the quantized score, the recovery percentage, and the exact command that reproduces it. Its numbers tell you where to point your own gate:

```
  general suite, 4k context      99.59% recovery
  harder suite, 4k context       99.54% recovery
  multimodal                    100.0%  recovery
  long-context suite at 131k     98.16% recovery   ← the lowest row
```

The long-context row is the lowest on the card, and no general suite covers it. That is the same conclusion the KV cache work reached independently.

**A composite gate, assembled from those sources.** Require 99% or better recovery on a general suite, 98% or better on a suite built from your own task, **a long-context evaluation at your real maximum context**, and a throughput run that proves the speed win you expected. State this as your own threshold, because no single source publishes it as policy.

**The sentence to remember:** quantization is a model change with a quality cost that standard benchmarks under-report, so gate it on your own task, at your real context length, with an interval rather than a point.

**The trap:** a 99% recovery score on a multiple-choice benchmark tells you almost nothing about open-ended generation, long context, or reasoning length. Human raters found 16% degradation where automatic metrics found 1.7%.

**Try this now:** run `python phase04_serving/quant_gate.py --self-test` and read the check named "a single flip is inside the noise". Then compute what accuracy difference your own eval set could detect, given its size.
---

## 4.5 — Speculative decoding (a bet with published odds)

Why this matters: Phase 1 established that decode is memory-bound. One token per step reads the whole model from GPU memory, and the arithmetic in between is cheap. Speculative decoding exploits that directly. If the arithmetic is nearly free, do more of it per memory read.

**The mechanism.** A cheap draft proposes k tokens. The target model verifies all k in **one** forward pass, which costs about the same as generating one token normally. Every token the target agrees with is kept. On disagreement, the target's own token replaces the rest.

```
  NORMAL DECODE                     SPECULATIVE DECODE
  step 1: read weights → 1 token    draft:  cheap, proposes 4 tokens
  step 2: read weights → 1 token    verify: ONE target pass over all 4
  step 3: read weights → 1 token            3 accepted, 1 rejected
  step 4: read weights → 1 token            + 1 free token from the target
  ────────────────────────────      ────────────────────────────────────
  4 weight reads, 4 tokens          1 weight read, 4 tokens
```

**The guarantee is stronger than people assume, and it is the reason this is safe.** The original paper proves the accepted tokens are "distributed identically to those sampled from the target alone". Not similar. Identical in distribution. That is why you can enable speculative decoding without re-running your evaluation suite, and it is the one optimisation in this phase with that property. Quantization does not have it. Neither does changing the model.

### The published formula, which is also the whole decision

The same paper gives the expected speedup exactly:

```
                     1 - alpha^(k+1)
  improvement =  ───────────────────────
                  (1 - alpha) (k*c + 1)

  alpha  per-position acceptance probability
  k      draft length
  c      cost of one draft step, as a fraction of one target step
```

The numerator saturates as k grows. The denominator keeps growing linearly. So there is an optimal k, and it shrinks as acceptance falls or as the draft gets more expensive.

`specdec_math.py` computes this. Run it:

```
python phase04_serving/specdec_math.py
```

```
┌───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┐
│ alpha │ k=1   │ k=2   │ k=3   │ k=4   │ k=5   │ k=6   │ k=7   │ k=8   │
├───────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┤
│  0.30 │  1.18 │  1.16 │  1.09 │  1.02 │  0.95 │  0.89 │  0.84 │  0.79 │
│  0.50 │  1.36 │  1.46 │  1.44 │  1.38 │  1.31 │  1.24 │  1.17 │  1.11 │
│  0.70 │  1.55 │  1.82 │  1.95 │  1.98 │  1.96 │  1.91 │  1.85 │  1.78 │
│  0.90 │  1.73 │  2.26 │  2.65 │  2.93 │  3.12 │  3.26 │  3.35 │  3.40 │
└───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘
```

Read the 0.30 row. At a 30% acceptance rate, drafting five tokens is **slower** than not speculating at all. Acceptance dominates everything.

### The number your server reports is not the number in the formula

This trips people up, and it is worth slowing down for.

vLLM reports a metric called `draft_acceptance_rate`. That is the fraction of **all drafted tokens** that survived, averaged across positions. The formula's `alpha` is the probability that **one** position survives. They are different quantities, related by:

```
  mean_acceptance_length = 1 + k * draft_acceptance_rate
```

Here is why it matters. Published measurements on a real workload, an H200 serving a 120B model with a trained draft head:

```
┌───┬──────────────┬───────────────┬───────────────┬─────────────┐
│ k │ server rate  │ length, theirs│ length, 1+k*r │ true alpha  │
├───┼──────────────┼───────────────┼───────────────┼─────────────┤
│ 2 │       0.454  │          1.91 │         1.908 │       0.577 │
│ 3 │       0.356  │          2.07 │         2.068 │       0.567 │
│ 4 │       0.283  │          2.13 │         2.132 │       0.555 │
└───┴──────────────┴───────────────┴───────────────┴─────────────┘
```

Columns 3 and 4 agree to three decimals, which confirms the identity on real data.

Now read the last column. The reported rate collapses from 0.454 to 0.283 as k rises, which looks like the draft model getting worse. **It is not.** The true per-position acceptance is roughly flat near 0.57. The reported rate falls only because it averages over more positions, and each position is less likely to survive than the one before it.

Reproduce this yourself:

```
python phase04_serving/specdec_math.py --from-server
```

**The practical consequence:** pick k using the formula and the converted alpha. Watching the reported rate drop and concluding "the draft is failing, lower k" will make you choose a k that is too small. This conversion is my own derivation from those published numbers, not a quoted result, so check it against your own server's metrics.

### The four methods, and what each costs to set up

```
┌──────────────────┬──────────────┬───────────────────┬────────────────────┐
│ method           │ setup cost   │ measured speedup  │ conditions         │
├──────────────────┼──────────────┼───────────────────┼────────────────────┤
│ n-gram / prompt  │ one config   │ 2.4x average;     │ summarisation and  │
│ lookup           │ line. No     │ 2.8x measured in  │ context QA, where  │
│                  │ model, no    │ vLLM              │ the answer copies  │
│                  │ training     │                   │ from the prompt    │
│ separate draft   │ zero if a    │ 1.5x              │ 70B target at one  │
│ model            │ small sibling│                   │ request per second │
│                  │ exists       │                   │                    │
│ Medusa heads     │ about 5 hours│ 2.2x to 3.6x      │ batch size 1, the  │
│                  │ on one A100  │                   │ paper says so      │
│ EAGLE-3          │ a training   │ up to 6.5x in the │ batch size 1, lab. │
│                  │ run, 1-2 days│ paper; 1.38x      │ Note the gap       │
│                  │ on 8 GPUs    │ throughput at     │ between those two  │
│                  │              │ batch 64          │ numbers            │
└──────────────────┴──────────────┴───────────────────┴────────────────────┘
```

**Start with n-gram.** It needs no model, no memory, and no training, and on the workloads where it fits it beats a draft model. It fits when the output copies from the input: summarisation, retrieval answers, code editing, and any agent loop that repeats context. It does nothing on turn one of a fresh chat, because there is nothing to copy yet.

A newer method, suffix decoding, extends that idea by caching sequences from previous outputs as well as the prompt, and reports up to 5.3x on agent workloads. It is a first-class method in the current vLLM.

### When it makes things worse

This is the part most write-ups omit, and it is the most useful thing in the section.

The whole technique rests on decode being memory-bound. Under load, the target's forward pass becomes compute-bound, and the extra verification tokens stop riding along for free. Then you are paying for draft work and extra verification and getting nothing.

**Measured, by the engine maintainers, same hardware and same models as their own wins:**

> at high QPS, 1.4x slowdown on Llama3-70B on ShareGPT with 4xH100, 1.8x slowdown on Llama3-70B on CNN DailyMail with 4xH100

The configuration that gained 1.5x at one request per second lost 1.4x under load. Only the load changed.

**A published crossover, from the EAGLE-3 paper's own table**, throughput relative to no speculation:

```
  batch size:    2      4      8     16     24     32     48     56
  EAGLE:      1.30x  1.25x  1.21x  1.10x  1.03x  0.93x  0.82x  0.71x
  EAGLE-3:    1.75x  1.68x  1.58x  1.49x  1.42x  1.36x  1.21x  1.01x
                                            ↑ EAGLE turns into a loss here
```

EAGLE falls below parity between batch 24 and 32. The improved method holds on to batch 56.

**The engine ships a feature specifically for this.** vLLM lets you vary the draft length by concurrency, and its own example configuration turns speculation **off entirely** above 129 concurrent requests:

```json
"num_speculative_tokens_per_batch_size": [
  [1, 64, 3],
  [65, 128, 1],
  [129, 512, 0]
]
```

That third row is the whole lesson expressed as configuration.

Reproduce the shape yourself:

```
python phase04_serving/specdec_math.py --sweep-batch
```

```
┌──────────────────┬──────────────────────┬─────────┬──────────────┐
│ verify overhead  │ roughly corresponds  │ best k  │ best speedup │
├──────────────────┼──────────────────────┼─────────┼──────────────┤
│           0.00   │ batch 1, idle        │       4 │       1.98x  │
│           0.15   │ moderate load        │       2 │       1.46x  │
│           0.50   │ saturated            │       1 │       1.06x  │
│           0.80   │ saturated, big batch │       1 │       0.89x  │   <- a LOSS
└──────────────────┴──────────────────────┴─────────┴──────────────┘
```

### The exception that keeps it useful

"High batch size kills it" is the wrong rule. The right rule is: **is the target model still memory-bound?**

Long context and mixture-of-experts models stay memory-bound much longer, because reading a huge KV cache dominates the step. Published work reports 2.51x at batch sizes between 32 and 256 on long sequences, and about 2.0x at 32,000 tokens of context at batch 32. The 120B measurement quoted earlier held its gains out to 200 concurrent requests.

So the decision is workload-shaped, not batch-shaped. Measure it on yours.

**The sentence to remember:** speculative decoding is the only optimisation here that provably cannot change your output, and the only one whose benefit can turn negative purely because your traffic went up.

**The trap:** benchmarking it at batch size 1, shipping it, and never measuring again. Every headline speedup in the literature is a batch-size-1 number unless it says otherwise.

**Try this now:** run `python phase04_serving/specdec_math.py --best-k --alpha 0.3 --draft-cost 0.2` and read the verdict. Then find the acceptance rate at which that draft becomes worth running at all.
---

## 4.6 — The self-host decision (arithmetic, not preference)

Why this matters: everything before this section was mechanics. This is the part a senior engineer is actually asked for, usually in a meeting, usually with someone who has already decided the answer.

**The decision has four inputs and only one of them is the GPU price.**

```
  1. the hourly rate you pay          ← the number everyone argues about
  2. output tokens per second you     ← the number that decides it
     actually sustain
  3. your UTILISATION                 ← the number everyone forgets
  4. the API price you compare to     ← changes the answer completely
```

Input 3 is the one that dominates. A rented GPU bills every hour whether or not requests arrive. At 10% utilisation your cost per token is ten times the cost at full load, with no change to the hardware.

### Run it

```
python phase04_serving/gpu_economics.py --gpu-hourly 3.49 --tps 1200 --role cheap
```

Output on this machine, one H100 at a verified rate, sustaining 1,200 output tokens per second, compared against a cheap API model at $1.60 per million output tokens:

```
┌──────────────┬────────────────────┬──────────────┬──────────────────┐
│ utilisation  │ output tokens/month│ $ per Mtok   │ vs the API       │
├──────────────┼────────────────────┼──────────────┼──────────────────┤
│         5%   │              158 M │ $   11.5741 │ 7.23x  more      │
│        20%   │              631 M │ $    2.8935 │ 1.81x  more      │
│        35%   │            1,104 M │ $    1.6534 │ 1.03x  more      │
│        50%   │            1,577 M │ $    1.1574 │ 0.72x  CHEAPER   │
│       100%   │            3,154 M │ $    0.5787 │ 0.36x  CHEAPER   │
└──────────────┴────────────────────┴──────────────┴──────────────────┘
```

Then the line that ends most of these conversations:

```
break-even volume, including the engineer: 3,484 million output tokens per month.
this fleet's ceiling at 100% utilisation:  3,154 million output tokens per month.
The break-even volume is ABOVE what this fleet can serve.
```

**Against a cheap API model, one GPU can never pay for itself**, once you include a quarter of an engineer. The fleet's own ceiling is below its break-even. No amount of tuning fixes that, because it is an arithmetic result, not an efficiency result.

Now change one input, the API you compare against:

```
python phase04_serving/gpu_economics.py --gpu-hourly 3.49 --tps 1200 --role deep
```

Break-even utilisation drops from 36% to about 11%. Against a frontier-priced model the same hardware pays for itself at a small fraction of its capacity.

**So the honest answer to "should we self-host" is a question: which API are you actually replacing?** Replacing a cheap small model almost never works. Replacing a frontier model often does.

### The engineer line

The script includes a quarter of one engineer at $180,000 a year, which is $3,750 a month. On a single-GPU fleet that is **twice the hardware cost**. Change those numbers to yours, but do not delete the line. A serving deployment needs someone who owns upgrades, incidents, capacity, and the evaluation gate from 4.4. That person is not free, and leaving them out of the comparison is how these proposals get approved and then regretted.

### What published break-even estimates say, and why they disagree

Three write-ups from 2026 reach different conclusions on similar hardware:

```
┌────────────────────────────┬───────────────────┬───────────────────────────┐
│ source                     │ assumed throughput│ conclusion                │
├────────────────────────────┼───────────────────┼───────────────────────────┤
│ a cost-tooling vendor      │ ~8,000 tok/s on   │ break-even at ~17% raw,   │
│                            │ one H100          │ 50-80% with ops overhead  │
│ a deployment platform      │ ~1,100 tok/s on   │ against a budget API tier,│
│                            │ one GPU           │ break-even is impossible  │
│ an independent site        │ 620 tok/s across  │ loses even at 100%        │
│                            │ 8 GPUs            │ utilisation, by 11x       │
└────────────────────────────┴───────────────────┴───────────────────────────┘
```

The throughput assumptions differ by more than 7x. Different models, different batch sizes, different context lengths. **Do not average them, and do not cite any of them as your number.** Two of the three are written by companies selling something adjacent, and none is peer reviewed.

They agree on one thing, and it is the useful part: the break-even volume moves by two orders of magnitude depending only on which API you compare against.

### Measure your own throughput or the whole exercise is theatre

Every number above depends on `--tps`, and `--tps` is the one input you cannot look up. It depends on your model, your quantization, your context length, your batch size, and your engine. That is what section 4.3 was for.

```
python phase04_serving/bench_client.py --base-url http://localhost:8000/v1 \
    --model <your-model> --concurrency 1,4,16,64 --trace phase04_serving/traces/support.jsonl
```

Take the peak output tokens per second from that run and feed it in. A vendor's throughput figure was produced on a workload that is not yours.

### The reasons that are not about money

Cost is the easiest input to compute and often the wrong reason to decide. Self-hosting also buys:

- **Data control.** Nothing leaves your network. For some regulated workloads this ends the discussion before cost is mentioned.
- **A model you cannot rent.** A fine-tune, a merged model, or an open-weight model no provider hosts.
- **Latency floor control.** No shared queue, no other tenants, no provider incident.
- **Price stability.** Your cost per token stops changing when a provider updates a price sheet.

And it costs you things the arithmetic does not show: you now own capacity planning, GPU supply, engine upgrades, security patching, and the pager.

**The sentence to remember:** self-hosting is a utilisation bet against a specific API price, so name the API and measure your own throughput before anyone argues about GPU rates.

**The trap:** comparing your GPU cost per token against an API's cost per token at 100% utilisation. Nobody runs at 100%. Run the sweep and find your real number.

**Try this now:** run `gpu_economics.py` twice, once with `--role cheap` and once with `--role deep`, and write down both break-even utilisations. That pair of numbers is the answer you bring to the meeting.
---

## 🧪 Hands-on lab — part B

Five of these seven exercises are offline. E12 and E13 need a rented GPU and together cost about $2 to $3.

**Live-run status:** the offline scripts were executed on 2026-09-13 and their printed outputs are real. No GPU was rented, so E12 and E13 were not executed. Their flags were verified against the engine source at the release tags.

- [ ] **E8 (offline).** Find where drafting stops paying.
  - Run: `python phase04_serving/specdec_math.py`
  - Expected: at an acceptance rate of 0.30, a draft length of 5 is already slower than not speculating. At 0.90, longer drafts keep helping past k=8.
  - Write down the best draft length for each acceptance rate in the table.
  - Teaches: acceptance rate dominates every other choice in speculative decoding.

- [ ] **E9 (offline).** Convert your server's metric into the one the formula needs.
  - Run: `python phase04_serving/specdec_math.py --from-server`
  - Expected: columns 3 and 4 agree to three decimals, confirming the identity on published measurements. The reported acceptance rate falls from 0.454 to 0.283 while the true per-position rate stays near 0.57.
  - Teaches: tuning by watching the reported rate fall will make you choose a draft length that is too small.

- [ ] **E10 (break-it, offline).** Watch a 2x speedup become a loss.
  - Run: `python phase04_serving/specdec_math.py --sweep-batch`
  - Expected: the best speedup falls from 1.98x to 0.89x as the verify pass stops being free, and the optimal draft length collapses from 4 to 1.
  - Then find the verify-overhead value at which it crosses 1.00x. That is your crossover.
  - Teaches: an optimisation measured on an idle GPU can be a regression on a paid one.

- [ ] **E11 (offline).** Find out what your eval set can actually detect.
  - Run: `python phase04_serving/quant_gate.py --self-test`
  - Expected: seven checks pass, including "a single flip is inside the noise".
  - Then answer: with 20 items, what is the smallest accuracy drop your gate could distinguish from zero? Compare that against the 2% default in `--max-drop`.
  - Teaches: a gate whose noise floor is wider than its threshold cannot fail.

- [ ] **E12 (needs a GPU, about $2).** Gate a real quantization change.
  - Serve the unquantized model on port 8000 and a published quantized checkpoint of the same model on port 8001. Do not quantize it yourself; download one whose publisher shipped an accuracy table.
  - Run: `python phase04_serving/quant_gate.py --baseline-url http://localhost:8000/v1 --baseline-model <fp16-id> --candidate-url http://localhost:8001/v1 --candidate-model <quant-id> --max-drop 0.02`
  - Expected: two accuracies, two throughputs, a delta with a 95% interval, and one word, SHIP or HOLD. Note whether the interval contains zero.
  - Teaches: the gate is the deliverable, not the quantized model.

- [ ] **E13 (break-it, needs a GPU, about $1).** Make an optimisation slower on purpose.
  - Serve with `--kv-cache-dtype fp8` and benchmark with **short** prompts, well under 7,000 tokens of context.
  - Run `bench_client.py` against it and against the same server without the flag.
  - Expected: the FP8 KV cache is slower or no faster at short context. The published break-even for one 8B model on an H100 is around 7,000 tokens.
  - Then rerun with a long-context trace and watch it reverse.
  - Teaches: an optimisation with a threshold is a regression below that threshold, and nothing warns you.

- [ ] **E14 (offline).** Answer the question you will actually be asked.
  - Run `python phase04_serving/gpu_economics.py --gpu-hourly <your rate> --tps <your E5 peak> --role cheap`, then again with `--role deep`.
  - Expected: two break-even utilisations. Against the cheap model, the fleet may not be able to reach its own break-even at all.
  - Write both numbers down with your measured throughput next to them.
  - Teaches: "should we self-host" is answered by naming the API you are replacing, then doing arithmetic.
---

## 🔍 Check it yourself

1. Open `phase04_serving/specdec_math.py` and find `alpha_from_length`. Explain why a bisection is guaranteed to converge here, using the property of `expected_tokens` that the docstring names. Then state what the function returns when the measured length equals k+1, and what that means physically.
2. In the same file, find the `verify_overhead` term in `speedup`. Set it to zero on paper and show that the expression reduces to the published theorem. Then explain in one sentence what physical fact makes that term non-zero in production.
3. Open `phase04_serving/quant_gate.py` and find `bootstrap_ci`. It resamples pairs rather than resampling each side separately. Explain what that removes from the comparison, and why the interval gets tighter as a result.
4. In the same file, find the line that decides SHIP or HOLD. It uses `lo`, not the point estimate. Explain the failure mode that using the point estimate would cause, in terms of how often it happens.

---

## ✅ Checkpoint 4B — answer in your own words

1. Show the math. Your draft model achieves a true per-position acceptance of 0.65 and costs 12% of a target step. (a) Compute the expected tokens per verification at k=3. (b) Compute the speedup at k=3 at batch size 1. (c) Your server reports a `draft_acceptance_rate` of 0.40 at k=3. Show that this is consistent with your alpha. (d) A colleague sees 0.40 and says "acceptance is poor, lower k to 2". Say why that reasoning is wrong.

2. A colleague says: "We enabled speculative decoding and measured 2x in staging, so we are shipping it." Give two specific reasons production may be slower than staging, using section 4.5. Then name the configuration feature that exists specifically to handle this, and describe what its most aggressive setting does.

3. Show the math, then decide. You rent two GPUs at $2.79 per hour each. You measure 2,400 output tokens per second sustained. Your monthly output volume is 900 million tokens and you are replacing an API that charges $8.00 per million output tokens. (a) Compute the hardware cost per month. (b) Compute your utilisation at that volume. (c) Include a quarter of an engineer at $180,000 a year and compare against the API bill. (d) Now recompute (c) against an API charging $1.60 and state which decision changes.

4. This is broken. You quantized a reasoning model to 4-bit. Your evaluation suite shows accuracy within 1% of the baseline, so the gate passed. Two weeks later your output-token bill has risen 40%. (a) Name the cause. (b) Explain why the gate did not catch it. (c) Name the metric you must add to the gate. (d) Give the published example, with its numbers, that demonstrates this effect.

5. Design it. You must present a self-host recommendation to your team. Write the structure. Cover: the four inputs to the arithmetic, which one you must measure rather than look up, the two break-even numbers you will show, the non-cost reasons that could override the arithmetic, and the one line most proposals omit.

6. A colleague says: "The benchmarks show engine X is faster, so that settles it." Using the audited comparison in section 4.3, give the specific reason a single winner cannot be read from it. Then name two things that must be stated with any engine benchmark before you believe it.

<details>
<summary>Answer sketches — write yours first, then compare</summary>

1. (a) (1 − 0.65⁴) / (1 − 0.65) = (1 − 0.1785) / 0.35 = 2.347 tokens. (b) Speedup = 2.347 / (1 + 3 × 0.12) = 2.347 / 1.36 = 1.73x. (c) mean length = 1 + k × reported rate = 1 + 3 × 0.40 = 2.20, which is close to the 2.347 implied by alpha = 0.65, so the two are broadly consistent; solving exactly for alpha from a length of 2.20 gives about 0.61. (d) The reported rate falls as k rises purely because it averages over more positions, each less likely to survive than the last. It is not evidence that the draft got worse. Choose k from the formula using the converted alpha.

2. First, staging is usually idle, so the target model is memory-bound and the extra verification tokens ride along nearly free. In production the forward pass becomes compute-bound and they do not. Second, the workload may differ: a draft that matches on summarisation will not match on translation, where published guidance says the optimal draft length can be one or even zero. The feature is vLLM's per-batch-size draft length, and its most aggressive setting maps a concurrency range to a draft length of zero, which turns speculative decoding off entirely above that load.

3. (a) 2 × $2.79 × 730 = $4,073 per month. (b) Capacity at full load is 2,400 × 3,600 × 730 = 6,307 million tokens, so 900 million is about 14.3% utilisation. (c) Engineer cost is $180,000 × 0.25 / 12 = $3,750, so the total is $7,823. The API bill is 900 × $8.00 = $7,200. The API is cheaper by about $623, despite the hardware alone looking cheap. (d) Against a $1.60 API the bill is $1,440, and self-hosting is now worse by roughly $6,383. The decision flips decisively; nothing about the hardware changed.

4. (a) Quantization made the reasoning model produce far longer chains of thought to reach the same answers. (b) Accuracy is the only thing the gate measured, and accuracy barely moved. Output length is not reported by any standard benchmark. (c) Mean output tokens per item, compared against the baseline, with a threshold. (d) A 1.5B reasoning model on a maths benchmark went from 85.6% accuracy using 5,200 reasoning tokens at BF16 to 47.0% using 23,400 tokens at 3-bit AWQ. That configuration is more aggressive than yours, but the mechanism is the same: in up to 52% of failures the model reached the right answer in an intermediate step and failed to commit to it.

5. The four inputs are the hourly rate, the sustained output tokens per second, the utilisation, and the API price you are replacing. Throughput is the one you must measure, because it depends on your model, quantization, context length and batch size. Show two break-even numbers: the utilisation at which hardware beats the API, and the monthly token volume at which the total including people beats the API, one for each candidate API. The non-cost reasons that can override the arithmetic are data control, a model nobody hosts, a latency floor you control, and price stability. The line most proposals omit is the engineer, which on a single-GPU fleet is typically twice the hardware cost.

6. In that audited submission the winner flips with the quantization path: one engine led by 18 to 19% on the pre-quantized model while the other led by 2 to 12% on dynamic quantization, on the same machine with the same driver. Quoting a single winner means choosing a row. Before believing any engine benchmark, require the engine versions with their release tags, and the exact flag values on both sides rather than defaults. Both projects have now stopped publishing head-to-head numbers, which is itself informative.

</details>
---

## References & Further Learning

Every URL was fetched and checked on 2026-09-13. Part A carries the serving, benchmarking and GPU-rental references. This document carries quantization, speculative decoding and the economics.

### Quantization

**vLLM quantization index** — https://docs.vllm.ai/en/latest/features/quantization/
Read one thing on this page: the hardware compatibility matrix. It is the only place that publishes which format runs on which GPU as a table, and it eliminates most options before you compare anything else. Use the engine source for exact flag spellings, because the page groups methods by documentation page rather than by accepted value.

**"Give Me BF16 or Give Me Death"? Accuracy-Performance Trade-Offs in LLM Quantization** — Kurtic, Marques, Pandit, Kurtz, Alistarh. https://arxiv.org/abs/2411.02355
The accuracy baseline for the whole section: over 500,000 evaluations across three model sizes. Focus on the recovery tables for the numbers, then on the serving section for the split that matters in practice, where weight-only quantization wins at low concurrency and weight-and-activation wins under load.
Numbers with conditions: FP8 recovers 99.3% to 101.2% at every size. Four-bit weight-only recovers 96.1%, 97.4% and 98.9% at 8B, 70B and 405B on the harder suite, and the size effect vanishes on the easier one. Serving figures come from vLLM 0.6.4 on A6000, A100 and H100.

**How Does Quantization Affect Multilingual LLMs?** — Marchisio et al., Cohere. https://arxiv.org/abs/2407.03211
Read it immediately after the paper above, as the correction. It is the only study found that ran **human** evaluation alongside automatic benchmarks on the same checkpoints, which is what lets it contradict the automatic-metric literature rather than merely differ from it.
The number to carry: automatic metrics reported −0.3% and −1.7% degradation where human evaluators reported −16.6% and −16.0%. Focus also on the maths results, where a 35B model at four-bit lost 13.1% on average and 17.3% in one language.
Honest note: the paper is from July 2024 and tested model families from then. Present it as the last time anyone checked with humans, not as a current measurement.

**The State of FP8 KV-Cache and Attention Quantization in vLLM** — https://vllm.ai/blog/2026-04-22-fp8-kvcache
The best single source on KV cache quantization, because it publishes accuracy, latency, a break-even threshold, and a regression the team caused and fixed. Focus on the break-even table and the "when not to use it" list.
Numbers: break-even around 7,000 tokens of context for one 8B model on an H100, and around 22,000 for another. One model shape with a head dimension of 256 saw a 1.6x TTFT regression. A precision bug in attention accumulation once took a 128,000-token retrieval task from 91% to 13% accuracy, invisible at short context.
One fact that invalidates most older material: between two engine versions the break-even for one model moved from 24,889 tokens to 7,010. Any KV cache benchmark older than about a year is worthless.

**A published quantization gate** — https://huggingface.co/RedHatAI/Llama-4-Scout-17B-16E-Instruct-quantized.w4a16
Read this as a process artifact rather than an article. It ships the recipe, the baseline score, the quantized score, the recovery percentage, and the exact command that reproduces all of it. Copy its shape for your own gate.
The row that teaches the most: general suites at 4,000 tokens of context recover 99.5% or better, while the long-context suite at 131,000 tokens recovers 98.16%. The lowest row is the long-context one, and no general suite covers it.

**Quantized Reasoning Models Think They Need to Think Longer, but They Do Not** — Lotfi, Kirichenko, Li, Liu. https://arxiv.org/abs/2606.00206
The failure an accuracy gate cannot see. Focus on the accuracy-and-length tables and the analysis of where the failures come from.
Numbers with conditions: a 1.5B reasoning model on a maths benchmark went from 85.6% accuracy using 5,200 reasoning tokens at BF16 to 47.0% using 23,400 tokens at 3-bit. In up to 52% of failures the model reached the correct answer in an intermediate step and failed to commit. Three-bit on a 1.5B model is the far end of aggressive; treat the mechanism as general and the magnitudes as not transferable.

### Speculative decoding

**Fast Inference from Transformers via Speculative Decoding** — Leviathan, Kalman, Matias. ICML 2023.
https://arxiv.org/abs/2211.17192
The paper that defines the method and proves it is safe. Read Section 2.3 for the sampling rule and Appendix A.1 for the proof that accepted tokens are "distributed identically to those sampled from the target alone". That guarantee is why this is the one optimisation in Phase 4 you can enable without re-running your evaluation suite.
The arithmetic you will actually use is Equation 1 and Theorem 3.8, which `specdec_math.py` implements. Section numbers here come from the readable HTML rendering rather than the published PDF, so confirm them before quoting in a slide.

**Performance improvements with speculative decoding in vLLM for gpt-oss** — Red Hat Developer, 2026-04-16.
https://developers.redhat.com/articles/2026/04/16/performance-improvements-speculative-decoding-vllm-gpt-oss
The only source found that publishes acceptance rate, acceptance length and throughput for the same runs across a concurrency sweep. Focus on the draft-length table, which is the source of the conversion in section 4.5.
Conditions: vLLM 0.13.0, an H200, a 120B mixture-of-experts target with a trained draft head. Raising the draft length from 2 to 4 cut the reported acceptance rate from 45.4% to 28.3% and raised mean acceptance length only from 1.91 to 2.13.

**The slowdown, measured by the maintainers** — https://vllm.ai/blog/2024-10-17-spec-decode
Read it for one sentence, which reports 1.4x and 1.8x **slowdowns** on two datasets at high load, on the same hardware and models that gained at one request per second. The stated cause is that the system is already compute-bound. A talk by a vLLM contributor shows the same effect at 19:26 of https://www.youtube.com/watch?v=9ih0EmcXRHE.

**EAGLE-3** — https://arxiv.org/abs/2503.01840
Read its batch-size table rather than its headline speedup. The earlier method falls below parity between batch 24 and 32; the newer one holds to batch 56. Honest note: the table does not name the GPU, and it uses no tree structure with a maximum chain length of 2, so treat the crossover as a shape rather than a number for your hardware.

**Dynamic speculative decoding** — https://docs.vllm.ai/en/v0.29.0/features/speculative_decoding/dynamic_speculative_decoding/
The engine's own answer to the problem above: vary the draft length by concurrency. Its documented example turns speculation off entirely above 129 concurrent requests. Note that the older `speculative_disable_by_batch_size` field no longer exists.

**Measuring acceptance on your own server** — https://docs.vllm.ai/en/v0.29.0/features/speculative_decoding/acceptance_metrics/
The flag is `--per-request-spec-decode-metrics summary`, and it reports `mean_acceptance_length`, `draft_acceptance_rate` and an acceptance histogram. Read section 4.5 before interpreting the second one.

**Prompt lookup decoding** — https://github.com/apoorvumang/prompt-lookup-decoding
The method to try first, because it needs no model and no training. Measured 2.4x on summarisation and context question answering with a 7B model on one A100, and 2.8x in vLLM's own measurement. Its README is honest about the limit: much smaller gains on the first turn of a chat, because there is nothing to copy yet.

**Deep Dive: Optimizing LLM inference** — Julien Simon, 36 minutes.
https://www.youtube.com/watch?v=hMs8VNRy5Ys
Phase 1 used the first half of this talk and parked the rest. This is that debt. The video has real chapters: 11:15 continuous batching, 16:17 speculative decoding, 25:28 a small off-the-shelf draft model, 26:40 n-grams, 30:25 Medusa.
Watch 11:15 to 16:17 first even though it is not speculative decoding. Continuous batching is the reason speculative decoding stops helping under load, and the talk covers it immediately before.

### Economics

Published break-even estimates disagree by more than 7x on assumed throughput, and three of the four found are written by companies selling an adjacent product. None is peer reviewed. Section 4.6 summarises them rather than citing one as authoritative, and the reason is that their throughput assumptions cannot all describe the same workload. Measure your own with `bench_client.py` instead.

---

## Cheatsheet — part B

```
QUANTIZATION FORMATS
  FP8 W8A8    weights+activations  2x smaller  Ada/Hopper/Blackwell, AMD
  INT8 W8A8   weights+activations  ~2x         Turing onward, plus CPU
  AWQ W4A16   weights only         ~75% off    Turing-Hopper, NOT AMD GPU
  GPTQ W4A16  weights only         ~75% off    Volta onward
  NVFP4       weights (+acts)      3.5x vs FP16  Blackwell only
  MXFP4       MoE expert weights   4.25 bits/param
  AutoAWQ is DEPRECATED; the tooling moved to llm-compressor
  You usually DOWNLOAD a quantized checkpoint. --quantization is for ONLINE
  quantization only; a pre-quantized checkpoint is detected from its config.

WHAT IT COSTS IN QUALITY
  FP8 ~ lossless at every size (99.3%-101.2% recovery)
  4-bit recovery rises with model size: 96.1% / 97.4% / 98.9% at 8B/70B/405B
    and ONLY on a hard enough suite
  automatic metrics said -1.7%. HUMAN raters said -16.0%. Same checkpoint.
  damage concentrates: maths and reasoning > non-Latin scripts > long context
  reasoning models get LONGER as well as worse:
    85.6% acc / 5,200 tokens  ->  47.0% acc / 23,400 tokens   (3-bit, 1.5B)
    put OUTPUT LENGTH in the gate; no standard benchmark reports it

WHAT IT BUYS IN SPEED
  weight-only (W4A16)  -> DECODE faster   -> wins at LOW concurrency  (1.45x)
  weight+activation    -> decode AND      -> wins under LOAD          (1.87x)
    (W8A8)                prefill faster
  batch size 1 + short outputs -> mostly just memory

KV CACHE QUANTIZATION
  --kv-cache-dtype fp8  halves KV storage, and has a BREAK-EVEN in context:
    ~7,000 tokens (8B on H100) | ~22,000 tokens (another model)
    BELOW the threshold it is SLOWER
  head_dim 256 + prefill-heavy -> 1.6x TTFT REGRESSION
  a precision bug once took 128k retrieval from 91% -> 13%, invisible at 4k
  break-even moved 24,889 -> 7,010 tokens between two versions:
    ANY KV-CACHE BENCHMARK OVER A YEAR OLD IS WORTHLESS

THE GATE
  >=99% on a general suite | >=98% on YOUR task suite
  + a LONG-CONTEXT eval at your real maximum | + a throughput run
  judge on the WORST end of the interval, not the midpoint
  published noise examples that are NOT wins: AIME +2 pts, GSM-8K 100.8%,
    HumanEval 0.933 vs 0.930 on 164 problems (= half a problem)

SPECULATIVE DECODING
  the guarantee: output is distributed IDENTICALLY to the target. Not similar.
    so it needs no eval re-run. Quantization does.
  improvement = (1 - a^(k+1)) / ((1 - a)(k*c + 1))        Theorem 3.8
    a = per-position acceptance | k = draft length | c = draft cost ratio
  YOUR SERVER REPORTS A DIFFERENT NUMBER:
    mean_acceptance_length = 1 + k * draft_acceptance_rate
    reported 0.454 -> 0.283 as k rises, but TRUE alpha stays ~0.57
  methods: n-gram (zero setup, 2.4-2.8x) | draft model (1.5x) |
           Medusa (~5 GPU-hours, 2.2-3.6x) | EAGLE-3 (days, 6.5x lab)
  START WITH N-GRAM when the output copies from the input
  IT CAN LOSE: measured 1.4x and 1.8x SLOWDOWNS at high load, same hardware
    EAGLE crosses below 1.00x between batch 24 and 32
    vLLM ships num_speculative_tokens_per_batch_size to turn it OFF above a
    concurrency threshold
  the right question is NOT "is batch high" but "is the target still
    memory-bound". Long context and MoE stay memory-bound far longer.

THE SELF-HOST DECISION
  four inputs: hourly rate | sustained output tok/s | UTILISATION | which API
  MEASURE the throughput. It is the only input you cannot look up.
  $/Mtok = (hourly x gpus) / (tok_s x 3600 x utilisation / 1e6)
  include the engineer. On a 1-GPU fleet that is TWICE the hardware cost.
  against a CHEAP API one GPU may never reach its own break-even
  against a FRONTIER API the same fleet breaks even near 11-15% utilisation
  non-cost reasons that override the arithmetic: data control, a model nobody
    hosts, a latency floor you own, price stability

THE COMMANDS
  specdec_math.py                          the speedup table, offline
  specdec_math.py --from-server            convert the reported rate
  specdec_math.py --sweep-batch            find where it becomes a loss
  specdec_math.py --best-k --alpha X       optimal draft length
  quant_gate.py --self-test                the statistics, offline
  quant_gate.py --baseline-url ... --candidate-url ...   the gate, live
  gpu_economics.py --gpu-hourly X --tps Y --role cheap   then --role deep
```
